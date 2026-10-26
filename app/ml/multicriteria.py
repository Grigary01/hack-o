"""Многокритериальное ранжирование v2, без обучения и произвольных оценок LLM.

Идея: много почти одинаковых признаков не должны случайно увеличить важность
одной потребности. quietness и удалённость от баров частично описывают тишину,
вид на море и закат — вид из окна. Объединяем их в явно заданные группы.

Внутри группы — взвешенное среднее; вес группы — максимальный приоритет её
участников, а не сумма. Новая группа по умолчанию создаётся для каждой неизвестной
фичи, так что расширение YAML не теряет её из ранжирования.

Неизвестная удовлетворённость имеет диапазон [0,1]. Считаем нижнюю/верхнюю
оценки всей альтернативы. Это границы по отсутствующим данным, НЕ доверительный
интервал; измерительные ошибки известных фактов пока в него не включены.

F = (1-balance) * weighted_mean(group_utilities) + balance * min(group_utilities).
Положительный balance уменьшает компенсацию плохой группы отличной другой.
Сортируем по нижней границе, показываем обе. Hard-ограничения остаются отдельно.
"""
from collections import defaultdict

GROUPS = {'quietness_proxy':'quietness', 'nightlife_distance_m':'quietness',
          'soundproofing':'quietness', 'sea_view':'view', 'sunset_view':'view',
          'walking_distance_to_beach_m':'beach_access',
          'sea_view_potential':'view', 'sea_view_min_floor':'view',
          'sunset_view_potential':'view', 'sunset_view_min_floor':'view',
          'aircraft_noise_exposure':'quietness', 'aircraft_path_distance_m':'quietness',
          'beach_route_climb_m':'beach_access', 'beach_route_busy_crossings':'beach_access'}
LABELS = {'quietness':'Тишина и сон','view':'Вид из номера','beach_access':'Доступ к пляжу'}


def curve_match(value, curve):
    if curve.kind == 'lower':
        distance = max(0., value-curve.ideal_max)
    elif curve.kind == 'higher':
        distance = max(0., curve.ideal_min-value)
    else:
        distance = max(0., curve.ideal_min-value, value-curve.ideal_max)
    return max(0., 1-distance/curve.tolerance)


def aggregate(preferences, matches, balance=.25):
    groups = defaultdict(list)
    for pref in preferences:
        if pref.importance > 0:
            # «Рядом с барами» — доступ к развлечениям, а не потребность в тишине.
            group = ('nightlife_access' if pref.feature_key=='nightlife_distance_m' and pref.desired=='near'
                     else GROUPS.get(pref.feature_key,pref.feature_key))
            groups[group].append(pref)
    result = []
    for group,prefs in groups.items():
        denominator = sum(p.importance for p in prefs)
        known = sum(p.importance for p in prefs if matches[p.feature_key] is not None)
        earned = sum(p.importance*matches[p.feature_key] for p in prefs if matches[p.feature_key] is not None)
        result.append(dict(group=group,label=LABELS.get(group,group),weight=max(p.importance for p in prefs),
                           lower=earned/denominator,upper=(earned+denominator-known)/denominator,
                           coverage=known/denominator,features=[p.feature_key for p in prefs]))
    total = sum(g['weight'] for g in result)
    if not total:
        return dict(lower=0.,upper=0.,coverage=0.,score=None,groups=[])
    mean = lambda key:sum(g['weight']*g[key] for g in result)/total
    coverage=mean('coverage')
    lower=(1-balance)*mean('lower')+balance*min(g['lower'] for g in result)
    upper=(1-balance)*mean('upper')+balance*min(g['upper'] for g in result)
    return dict(lower=lower,upper=upper,coverage=coverage,
                score=mean('lower')/coverage if coverage else None,groups=result)


def mark_dominated(candidates):
    """Метка Парето: есть другой отель не хуже по всем известным пожеланиям.

Сравниваем только полностью известные одинаковые наборы критериев внутри
одной группы hard-результата. При неизвестностях доминирование не утверждаем.
Метку показываем для объяснения; кандидатов не удаляем.
"""
    vectors = {}
    for candidate in candidates:
        if candidate.eligible is not True:
            continue
        prefs=[c for c in candidate.criteria if c.outcome in ('preference','unknown') and c.match is not None]
        expected={key for g in candidate.group_scores for key in g['features']}
        if expected and {p.feature_key for p in prefs}==expected:
            vectors[candidate.hotel.id]={p.feature_key:p.match for p in prefs}
    for candidate in candidates:
        current=vectors.get(candidate.hotel.id)
        if current is None:
            continue
        candidate.pareto_dominated=any(other.keys()==current.keys() and
            all(other[k]>=current[k] for k in current) and any(other[k]>current[k] for k in current)
            for hid,other in vectors.items() if hid!=candidate.hotel.id)
