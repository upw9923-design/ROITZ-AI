"""Debug script to check endpoint behavior with seeded conversations."""
from fastapi.testclient import TestClient
from dashboard.server import DashboardServer
from memory.conversation_store import ConversationStore
from memory.conversation_models import Conversation
import tempfile
import pathlib
import json

temp_dir = tempfile.TemporaryDirectory()
store = ConversationStore(pathlib.Path(temp_dir.name) / 'test.sqlite3')

# Seed a conversation
base_ts = 1700000000000
conv = Conversation(
    id="conv-0000",
    title="Test Session 0",
    started_at=base_ts,
    turn_count=1,
    summary="Summary of session 0",
    language="en",
    engine="gemini_live",
)
created = store.create_conversation(conv)
print(f"Created conversation: {created}")

# Check what list_conversations returns
convs = store.list_conversations()
print(f"list_conversations returned: {list(convs)}")
print(f"Number of conversations: {store.count_conversations()}")

# Now test endpoint
server = DashboardServer()
server._conversation_store = store
client = TestClient(server.app)
key = server.new_key(3600)
resp = client.post('/login', json={'pin': key})
print(f"Login response: {resp.status_code} {resp.json()}")
token = resp.json()['token']

resp = client.get('/api/sessions', headers={'Authorization': f'Bearer {token}'})
print(f"Response status: {resp.status_code}")
print(f"Response JSON: {json.dumps(resp.json(), indent=2)}")

# Cleanup
store.close()
try:
    temp_dir.cleanup()
except Exception as e:
    print(f"Cleanup error (expected on Windows): {e}")