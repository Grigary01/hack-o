"""MapEngine: адаптация FeatureGroup/Marker/PolyLine из agent_tool_map (Maxim, MIT).

Текст OSM экранируется. Локальная SVG-схема доступна без CDN/тайлов;
Folium — дополнительная онлайн-карта. Линии — только рассчитанные пути.
"""
from html import escape
import folium


def get_routes(results):
    routes = []
    for result in results:
        for criterion in result['criteria']:
            if criterion['feature_key']=='walking_distance_to_beach_m':
                for obs in criterion['evidence']:
                    route = obs['evidence']['details'].get('coordinates',[])
                    if route:
                        routes.append(route)
    return routes


class MapEngine:
    def __init__(self,location):
        self.map = folium.Map(location=location,zoom_start=14,tiles='OpenStreetMap')

    def add_hotels(self,hotels):
        group = folium.FeatureGroup(name='Отели OSM')
        for hotel in hotels:
            folium.Marker([hotel['lat'],hotel['lon']],popup=escape(hotel['name']),
                          icon=folium.Icon(color='blue',icon='bed',prefix='fa')).add_to(group)
        group.add_to(self.map)

    def add_routes(self,routes):
        group = folium.FeatureGroup(name='Пешие пути: оценочные входы')
        for route in routes:
            folium.PolyLine([[lat,lon] for lon,lat in route],color='#167c80',weight=3).add_to(group)
        group.add_to(self.map)

    def render(self):
        folium.LayerControl().add_to(self.map)
        return self.map.get_root().render()


def offline_map(results):
    hotels = [r['hotel'] for r in results]
    routes = get_routes(results)
    points = [[h['lon'],h['lat']] for h in hotels]+[p for line in routes for p in line]
    if not points:
        return ''
    west,east = min(p[0] for p in points),max(p[0] for p in points)
    south,north = min(p[1] for p in points),max(p[1] for p in points)
    # Единый масштаб с поправкой cos(latitude); координатная схема, не топокарта.
    ratio = .726
    width,height = max((east-west)*ratio,.001),max(north-south,.001)
    scale = min(800/width,350/height)
    def xy(lon,lat):
        return 30+(lon-west)*ratio*scale,30+(north-lat)*scale
    pieces = ['<svg viewBox="0 0 860 420" role="img" aria-label="Схема отелей и путей до пляжа" style="width:100%;background:#eef5f5;border-radius:12px">',
              '<text x="800" y="28" fill="#243e55" font-size="15">С ↑</text>']
    for route in routes:
        values = ' '.join(f'{x:.1f},{y:.1f}' for x,y in (xy(*p) for p in route))
        pieces.append(f'<polyline points="{values}" fill="none" stroke="#167c80" stroke-width="2" opacity=".6"/>')
    for i,h in enumerate(hotels,1):
        x,y=xy(h['lon'],h['lat'])
        pieces.append(f'<g><title>{escape(h["name"])}</title><circle cx="{x}" cy="{y}" r="9" fill="#244fc0"/><text x="{x}" y="{y+4}" text-anchor="middle" font-size="10" fill="white">{i}</text></g>')
    pieces.append('<text x="30" y="410" font-size="12" fill="#42616e">Схема без подложки · оценочные входы · © OpenStreetMap contributors, ODbL</text></svg>')
    return ''.join(pieces)
