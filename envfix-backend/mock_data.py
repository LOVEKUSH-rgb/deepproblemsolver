import requests
import json

base_url = 'http://127.0.0.1:8000'

print('Creating team...')
res = requests.post(f'{base_url}/teams', json={'name': 'Test Engineering', 'avg_manual_fix_minutes': 20, 'hourly_rate': 100.0})
team = res.json()
team_id = team['id']
api_key = team['api_key']
print(f'Team created: ID={team_id}, Key={api_key}')

headers = {'X-API-Key': api_key}

print('Mocking successful fixes (should count towards savings)...')
for _ in range(5):
    requests.post(f'{base_url}/events', headers=headers, json={
        'error_type': 'ModuleNotFoundError',
        'provider_used': 'ollama',
        'was_cache_hit': False,
        'fix_applied': True,
        'fix_worked': True
    })

print('Mocking failed fix (should NOT count)...')
requests.post(f'{base_url}/events', headers=headers, json={
    'error_type': 'SyntaxError',
    'provider_used': 'groq',
    'was_cache_hit': False,
    'fix_applied': True,
    'fix_worked': False
})

print('Mocking cache hits (should NOT count towards savings, as per spec)...')
for _ in range(3):
    requests.post(f'{base_url}/events', headers=headers, json={
        'error_type': 'ImportError',
        'provider_used': 'ollama',
        'was_cache_hit': True,
        'fix_applied': True,
        'fix_worked': True
    })

print('Fetching stats...')
stats_res = requests.get(f'{base_url}/teams/{team_id}/stats', headers=headers)
print(json.dumps(stats_res.json(), indent=2))

print(f'\n--- Use these credentials on the dashboard ---')
print(f'Team ID: {team_id}')
print(f'API Key: {api_key}')
