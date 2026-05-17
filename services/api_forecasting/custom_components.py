"""
Custom Keras components yang dipakai V3 forecasting model.
Dipisah ke file sendiri biar bisa di-import saat load model.
"""
import tensorflow as tf
from tensorflow.keras import layers


@tf.keras.utils.register_keras_serializable()
class TemporalAttentionLayer(layers.Layer):
    """Self-attention sederhana untuk weighted sum across timesteps."""

    def __init__(self, units=32, **kwargs):
        super().__init__(**kwargs)
        self.units = units

    def build(self, input_shape):
        self.W = self.add_weight(
            name='att_w', shape=(input_shape[-1], self.units),
            initializer='glorot_uniform', trainable=True,
        )
        self.b = self.add_weight(
            name='att_b', shape=(self.units,),
            initializer='zeros', trainable=True,
        )
        self.u = self.add_weight(
            name='att_u', shape=(self.units, 1),
            initializer='glorot_uniform', trainable=True,
        )

    def call(self, x):
        score = tf.tanh(tf.matmul(x, self.W) + self.b)
        attention_weights = tf.nn.softmax(tf.matmul(score, self.u), axis=1)
        return tf.reduce_sum(attention_weights * x, axis=1)

    def get_config(self):
        cfg = super().get_config()
        cfg.update({'units': self.units})
        return cfg


@tf.keras.utils.register_keras_serializable()
class AsymmetricHuberLoss(tf.keras.losses.Loss):
    """Huber loss yang menalti under-prediction lebih berat."""

    def __init__(self, delta=1.0, under_weight=1.5, **kwargs):
        super().__init__(**kwargs)
        self.delta = delta
        self.under_weight = under_weight

    def call(self, y_true, y_pred):
        err = y_true - y_pred
        abs_err = tf.abs(err)
        huber = tf.where(
            abs_err <= self.delta,
            0.5 * tf.square(err),
            self.delta * (abs_err - 0.5 * self.delta),
        )
        weighted = tf.where(err > 0, huber * self.under_weight, huber)
        return tf.reduce_mean(weighted)

    def get_config(self):
        cfg = super().get_config()
        cfg.update({'delta': self.delta, 'under_weight': self.under_weight})
        return cfg


CUSTOM_OBJECTS = {
    'TemporalAttentionLayer': TemporalAttentionLayer,
    'AsymmetricHuberLoss': AsymmetricHuberLoss,
}
