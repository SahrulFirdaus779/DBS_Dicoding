import os
import numpy as np
import joblib
import tensorflow as tf

# Define custom objects required to load the model
class DonorAttentionLayer(tf.keras.layers.Layer):
    def __init__(self, units: int, dropout_rate: float = 0.3, **kwargs):
        super().__init__(**kwargs)
        self.units = units
        self.dropout_rate = dropout_rate

    def build(self, input_shape):
        d = input_shape[-1]
        gi = tf.keras.initializers.GlorotUniform()
        zi = tf.keras.initializers.Zeros()
        self.W_a = self.add_weight(name='W_a', shape=(d, 1), initializer=gi, trainable=True)
        self.b_a = self.add_weight(name='b_a', shape=(1,), initializer=zi, trainable=True)
        self.W_o = self.add_weight(name='W_o', shape=(d, self.units), initializer=gi, trainable=True)
        self.b_o = self.add_weight(name='b_o', shape=(self.units,), initializer=zi, trainable=True)
        self.drop = tf.keras.layers.Dropout(self.dropout_rate)
        super().build(input_shape)

    def call(self, x, training=False):
        attn = tf.nn.sigmoid(tf.matmul(x, self.W_a) + self.b_a)
        gated = self.drop(x * attn, training=training)
        return tf.nn.relu(tf.matmul(gated, self.W_o) + self.b_o)

    def get_config(self):
        cfg = super().get_config()
        cfg.update({'units': self.units, 'dropout_rate': self.dropout_rate})
        return cfg

class WeightedFocalLoss(tf.keras.losses.Loss):
    def __init__(self, gamma=2.0, class_weights=None, **kwargs):
        super().__init__(**kwargs)
        self.gamma = gamma
        self.class_weights = class_weights

    def call(self, y_true, y_pred):
        y_pred = tf.clip_by_value(y_pred, 1e-7, 1 - 1e-7)
        ce = -y_true * tf.math.log(y_pred)
        p_t = tf.reduce_sum(y_true * y_pred, axis=-1, keepdims=True)
        loss = tf.pow(1 - p_t, self.gamma) * ce
        if self.class_weights is not None:
            cw = tf.constant(self.class_weights, dtype=tf.float32)
            sw = tf.reduce_sum(y_true * cw, axis=-1, keepdims=True)
            loss = loss * sw
        return tf.reduce_mean(tf.reduce_sum(loss, axis=-1))

    def get_config(self):
        cfg = super().get_config()
        cfg.update({'gamma': self.gamma, 'class_weights': self.class_weights})
        return cfg

CUSTOM_OBJECTS = {
    'DonorAttentionLayer': DonorAttentionLayer,
    'WeightedFocalLoss': WeightedFocalLoss,
}

FEATURE_COLS = [
    'recency_days', 'log_frequency', 'log_monetary_total',
    'log_monetary_avg', 'log_monetary_max', 'log_monetary_std',
    'tenure_days', 'n_unique_programs', 'n_unique_channels',
    'pct_zakat', 'pct_infaq', 'pct_kemanusiaan', 'pct_pendidikan',
    'pct_sedekah', 'pct_wakaf', 'pct_yatim', 'pct_qurban', 'pct_other',
    'pct_weekend', 'pct_ramadan',
    'inter_arrival_avg_days', 'inter_arrival_std_days',
    'has_real_phone',
]

RAW_TO_LOG = ['monetary_total', 'monetary_avg', 'monetary_max',
              'monetary_min', 'monetary_median', 'monetary_std', 'frequency']

class SegmentationModel:
    def __init__(self, model_dir):
        model_path = os.path.join(model_dir, 'zakatsight_segmentasi_v2.keras')
        scaler_path = os.path.join(model_dir, 'scaler_segmentasi_v2.pkl')
        encoder_path = os.path.join(model_dir, 'label_encoder_v2.pkl')
        
        if not os.path.exists(model_path):
            self.model = None
            return

        self.model = tf.keras.models.load_model(model_path, custom_objects=CUSTOM_OBJECTS)
        self.scaler = joblib.load(scaler_path)
        self.encoder = joblib.load(encoder_path)

    def is_loaded(self):
        return self.model is not None

    def preprocess(self, donor_data: dict) -> np.ndarray:
        d = dict(donor_data)
        for col in RAW_TO_LOG:
            if col in d:
                d[f'log_{col}'] = float(np.log1p(d[col]))

        feat_vec = np.array([[d.get(col, 0.0) for col in FEATURE_COLS]], dtype=np.float32)
        feat_scaled = self.scaler.transform(feat_vec).astype(np.float32)
        return feat_scaled

    def predict(self, donor_data: dict) -> dict:
        if not self.is_loaded():
            return {'segment': 'Unknown', 'confidence': 0.0, 'all_probabilities': {}}
            
        feat_scaled = self.preprocess(donor_data)
        probs = self.model.predict(feat_scaled, verbose=0)[0]
        
        idx = int(np.argmax(probs))
        segment = self.encoder.classes_[idx]
        confidence = float(probs[idx])
        
        all_probs = {self.encoder.classes_[i]: round(float(probs[i]), 4)
                     for i in range(len(self.encoder.classes_))}
                     
        return {
            'segment': segment,
            'confidence': round(confidence, 4),
            'all_probabilities': all_probs,
        }
