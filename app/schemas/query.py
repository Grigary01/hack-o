"""ML → Backend контракт: форма результата понимания текста.

Pydantic превращает проверенный dict/JSON в объект с полями и отклоняет
некорректные значения. Эти классы описывают ЖЕЛАНИЯ гостя, не факты отеля.
JSON Schema для Ollama строится из тех же классов автоматически.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator
from app.features.registry import get_registry

# Strict-типы не допускают удобного, но опасного приведения «true» → True
# или True → 1 метр. Проверка допустимого типа каждой фичи идёт ещё и в registry.
Value = StrictBool | StrictInt | StrictFloat | StrictStr


class Contract(BaseModel):
    # Неизвестные поля не игнорируются; NaN/Infinity нельзя пустить в расстояния/веса.
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class HardConstraint(Contract):
    """Обязательное условие: например, расстояние до пляжа <= 500 метров.

    scope='hotel' относится к объекту целиком; scope='room' — к одному номеру.
    Строгое условие нельзя компенсировать другой хорошей характеристикой.
    """
    feature_key: str
    operator: Literal['<', '<=', '=', '>=', '>', '!=']
    value: Value
    unit: str | None = None
    scope: Literal['hotel', 'room'] = 'hotel'

    @model_validator(mode='after')
    def check_feature(self):
        # after: базовые типы уже проверены, теперь проверяем связи между полями.
        registry = get_registry()
        definition = registry.get(self.feature_key)
        if definition.type == 'number' and self.unit == 'km' and type(self.value) in (int,float):
            # Единая внутренняя единица позволяет честно сравнить .5 км с 319.8 м.
            self.value *= 1000
            self.unit = 'm'
        registry.validate_value(self.feature_key, self.value)
        if self.scope != definition.scope or self.unit != definition.unit:
            raise ValueError('Неверные scope или unit')
        if definition.type != 'number' and self.operator not in ('=', '!='):
            raise ValueError('Порядковые операторы допустимы только для чисел')
        return self


class UtilityCurve(Contract):
    """Числовая цель и плавное ухудшение. Все числа в единицах feature registry.

lower: идеально <= ideal_max; higher: идеально >= ideal_min;
target_range: идеально внутри [ideal_min, ideal_max]. На расстоянии tolerance
за пределами идеальной области удовлетворённость равна 0. Это предпочтение,
а не обязательное ограничение: запрет задаётся отдельно в hard_constraints.
"""
    kind: Literal['lower', 'higher', 'target_range']
    ideal_min: float | None = None
    ideal_max: float | None = None
    tolerance: float = Field(gt=0)

    @model_validator(mode='after')
    def coherent(self):
        if self.kind in ('higher','target_range') and self.ideal_min is None:
            raise ValueError('Нужен ideal_min')
        if self.kind in ('lower','target_range') and self.ideal_max is None:
            raise ValueError('Нужен ideal_max')
        if self.kind == 'lower' and self.ideal_min is not None:
            raise ValueError('Для lower нужен только ideal_max')
        if self.kind == 'higher' and self.ideal_max is not None:
            raise ValueError('Для higher нужен только ideal_min')
        if self.ideal_min is not None and self.ideal_max is not None and self.ideal_min > self.ideal_max:
            raise ValueError('Границы диапазона переставлены')
        return self


class SoftPreference(Contract):
    """Пожелание для ранжирования: desired и importance (от 0 до 1).

    importance не является уверенностью модели. Это настройка приоритета:
    default — правило команды, explicit — задано пользователем,
    relative_inferred — интерпретация «тишина важнее вида».
    """
    feature_key: str
    desired: Value
    importance: float = Field(default=0.5, ge=0, le=1)
    weight_source: Literal['default', 'explicit', 'relative_inferred', 'companion'] = 'default'
    scope: Literal['hotel', 'room'] = 'hotel'
    utility: UtilityCurve | None = None
    # Заполняет только backend (app/ml/companions.py): из какого желания гостя
    # выведено это расчётное пожелание. Парсер/LLM это поле не задаёт.
    derived_from: str | None = None

    @model_validator(mode='after')
    def check_feature(self):
        registry = get_registry()
        definition = registry.get(self.feature_key)
        if self.scope != definition.scope:
            raise ValueError('Неверный scope')
        if self.utility is not None:
            if definition.type != 'number':
                raise ValueError('Числовая кривая допустима только для числового свойства')
            for value in (self.utility.ideal_min,self.utility.ideal_max):
                if value is not None:
                    registry.validate_value(self.feature_key,value)
        if definition.type == 'number' and self.desired in ('near', 'far'):
            pass
        else:
            registry.validate_value(self.feature_key, self.desired)
        if (self.weight_source == 'companion') != (self.derived_from is not None):
            raise ValueError('companion-вес требует derived_from, и наоборот')
        if self.weight_source == 'default':
            # Модель не может выдать случайный вес за «стандартный»:
            # доверяем default_weight из нашего YAML, не её числу.
            self.importance = definition.default_weight
        return self


class ParsedHotelQuery(Contract):
    """Полный результат parser: регион, hard/soft, непонятое и исходный текст.

    unknown_or_ambiguous нужен, чтобы ограничение не исчезло молча.
    Например, «до 5000 рублей» нельзя поддержать без цен — backend попросит уточнить.
    """
    region: str = 'Adler'
    hard_constraints: list[HardConstraint] = Field(default_factory=list, max_length=12)
    soft_preferences: list[SoftPreference] = Field(default_factory=list, max_length=12)
    unknown_or_ambiguous: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    original_text: str = ''

    @model_validator(mode='after')
    def unique_preferences(self):
        keys = [x.feature_key for x in self.soft_preferences]
        if len(set(keys)) != len(keys):
            raise ValueError('Предпочтения не должны дублироваться')
        return self
