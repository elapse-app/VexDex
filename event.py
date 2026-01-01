from datetime import datetime

class Event:
    id = 0
    sku = ''
    name = ''
    start = datetime.min
    end = datetime.max
    season_id = 197
    divisions_id = []

    @staticmethod
    def from_json(json):
        event = Event()
        event.id = json['id']
        event.sku = json['sku']
        event.name = json['name']
        event.start = datetime.fromisoformat(json['start'])
        event.end = datetime.fromisoformat(json['end'])
        event.season_id = json['season']['id']
        event.divisions_id = []
        for i in range(len(json['divisions'])):
            event.divisions_id.append(json['divisions'][i]['id'])

        return event

    def __repr__(self):
        return f'Event {self.id}: {self.sku}'

    def __str__(self):
        return f'Event {self.id}: {self.sku}'