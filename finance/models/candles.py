from marshmallow_mongoengine import ModelSchema
from mongoengine import Document, FloatField, IntField, BooleanField


class Candle(Document):  # todo __init__??
    open = FloatField()
    high = FloatField()
    low = FloatField()
    close = FloatField()
    volume = FloatField()
    open_time = IntField()
    close_time = IntField()
    # is_completed = BooleanField()
    meta = {'indexes': ['open_time'], 'abstract': True}  # Keeping all data of child classes in same collection
    #     meta = {'indexes': ['open_time'], 'allow_inheritance': True}

    def __str__(self):
        return f"{self.open}, {self.high}, {self.low}, {self.close}, {self.volume}, {self.open_time}," \
               f" {self.close_time}"  # , {self.is_completed}

    def to_dict(self):
        return {
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'open_time': self.open_time,
            'close_time': self.close_time
        }

    def clone(self):
        return Candle(open=self.open, high=self.high, low=self.low, close=self.close, volume=self.volume,
                      open_time=self.open_time, close_time=self.close_time)  # is_completed=self.is_completed


class Candle1m(Candle):  # todo check mongodb performance
    pass


class Candle1mSchema(ModelSchema):
    class Meta:
        model = Candle1m


class Candle15m(Candle):
    pass


class Candle15mSchema(ModelSchema):
    class Meta:
        model = Candle15m


class Candle1h(Candle):
    pass


class Candle1hSchema(ModelSchema):
    class Meta:
        model = Candle1h


class Candle4h(Candle):
    pass


class Candle4hSchema(ModelSchema):
    class Meta:
        model = Candle4h
