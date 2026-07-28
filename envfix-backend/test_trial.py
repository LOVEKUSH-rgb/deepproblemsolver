import requests
import json

base_url = 'http://127.0.0.1:8000'

print('Creating team...')
res = requests.post(f'{base_url}/teams', json={'name': 'Trial Test Engineering', 'avg_manual_fix_minutes': 20, 'hourly_rate': 100.0})
team = res.json()
team_id = team['id']
api_key = team['api_key']
print(f'Team created: ID={team_id}, Key={api_key}')

headers = {'X-API-Key': api_key}

print('Sending 101 events to hit the limit of 100...')
events_sent = 0
for i in range(101):
    r = requests.post(f'{base_url}/events', headers=headers, json={
        'error_type': 'ModuleNotFoundError',
        'provider_used': 'ollama',
        'was_cache_hit': False,
        'fix_applied': True,
        'fix_worked': True
    })
    if r.status_code == 200:
        events_sent += 1
    else:
        print(f'Blocked at event {i+1}: {r.status_code} - {r.json()}')
        break

print(f'Total events successfully sent: {events_sent}')

print('Fetching stats...')
stats_res = requests.get(f'{base_url}/teams/{team_id}/stats', headers=headers)
print(json.dumps(stats_res.json(), indent=2))

print(f'\n--- Use these credentials on the dashboard ---')
print(f'Team ID: {team_id}')
print(f'API Key: {api_key}')
