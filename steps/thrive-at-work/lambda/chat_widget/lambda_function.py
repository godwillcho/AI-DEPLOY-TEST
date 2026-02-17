"""
Stability360 Thrive@Work — Chat Widget Lambda
───────────────────────────────────────────────
Serves a self-contained chat page that connects to the Thrive@Work AI bot
via Amazon Connect StartChatContact + Participant Service.

Routes:
  GET  /           → HTML chat page
  POST /start-chat → Calls StartChatContact, returns participantToken
  POST /send       → (Proxied from frontend) Not needed — frontend talks
                      directly to Connect Participant Service via WebSocket

Environment variables:
  CONNECT_INSTANCE_ID  — Connect instance ID
  CONTACT_FLOW_ID      — Thrive-at-Work contact flow ID
  CONNECT_REGION       — AWS region (default: us-west-2)
"""

import boto3
import json
import logging
import os
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

INSTANCE_ID = os.environ.get('CONNECT_INSTANCE_ID', '')
CONTACT_FLOW_ID = os.environ.get('CONTACT_FLOW_ID', '')
REGION = os.environ.get('CONNECT_REGION', 'us-west-2')

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
}


def _json_response(status, body):
    return {
        'statusCode': status,
        'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
        'body': json.dumps(body),
    }


def _html_response(html):
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html; charset=utf-8'},
        'body': html,
    }


def handle_start_chat(event):
    """Start a new chat contact and return the participant token."""
    try:
        body = json.loads(event.get('body', '{}'))
    except Exception:
        body = {}

    display_name = body.get('displayName', 'Customer')

    connect = boto3.client('connect', region_name=REGION)

    resp = connect.start_chat_contact(
        InstanceId=INSTANCE_ID,
        ContactFlowId=CONTACT_FLOW_ID,
        ParticipantDetails={'DisplayName': display_name},
        ChatDurationInMinutes=60,
    )

    contact_id = resp['ContactId']
    participant_token = resp['ParticipantToken']

    logger.info('Chat started: contactId=%s', contact_id)

    return _json_response(200, {
        'contactId': contact_id,
        'participantToken': participant_token,
        'region': REGION,
    })


def handle_page(event):
    """Serve the chat widget HTML page."""
    return _html_response(CHAT_PAGE_HTML)


def lambda_handler(event, context):
    """Route requests."""
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path = event.get('rawPath', '/')

    # CORS preflight
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': ''}

    if method == 'POST' and path == '/start-chat':
        return handle_start_chat(event)

    return handle_page(event)


# ─────────────────────────────────────────────────────────────────────
# Inline HTML — self-contained chat widget
# ─────────────────────────────────────────────────────────────────────

CHAT_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stability360 Thrive@Work</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%);
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
  }
  .chat-container {
    width: 440px; max-width: 95vw; height: 700px; max-height: 90vh;
    background: #fff; border-radius: 16px; overflow: hidden;
    box-shadow: 0 25px 60px rgba(0,0,0,0.4); display: flex; flex-direction: column;
  }
  .chat-header {
    background: linear-gradient(135deg, #10264a, #1a3a6b);
    color: #fff; padding: 18px 24px; flex-shrink: 0;
  }
  .chat-header h1 { font-size: 18px; font-weight: 700; margin-bottom: 2px; }
  .chat-header p { font-size: 12px; opacity: 0.8; }
  .chat-messages {
    flex: 1; overflow-y: auto; padding: 16px; background: #f8fafc;
    display: flex; flex-direction: column; gap: 12px;
  }
  .msg { max-width: 82%; padding: 12px 16px; border-radius: 16px; line-height: 1.5;
         font-size: 14px; word-wrap: break-word; animation: fadeIn 0.3s ease; }
  .msg.bot { background: #fff; color: #1f2937; align-self: flex-start;
             border: 1px solid #e5e7eb; border-bottom-left-radius: 4px; }
  .msg.user { background: #10264a; color: #fff; align-self: flex-end;
              border-bottom-right-radius: 4px; }
  .msg.system { background: #fef3c7; color: #92400e; align-self: center;
                font-size: 13px; text-align: center; border-radius: 8px; }
  .msg .sender { font-size: 11px; font-weight: 600; margin-bottom: 4px; opacity: 0.7; }
  .typing { align-self: flex-start; padding: 12px 20px; background: #fff;
            border: 1px solid #e5e7eb; border-radius: 16px; }
  .typing span { display: inline-block; width: 8px; height: 8px; background: #94a3b8;
                 border-radius: 50%; animation: bounce 1.4s infinite; margin: 0 2px; }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  .chat-input {
    display: flex; padding: 12px 16px; background: #fff; border-top: 1px solid #e5e7eb;
    gap: 8px; flex-shrink: 0;
  }
  .chat-input input {
    flex: 1; padding: 12px 16px; border: 2px solid #e5e7eb; border-radius: 24px;
    font-size: 14px; outline: none; transition: border-color 0.2s;
  }
  .chat-input input:focus { border-color: #10264a; }
  .chat-input input:disabled { background: #f3f4f6; }
  .chat-input button {
    padding: 12px 20px; background: #10264a; color: #fff; border: none;
    border-radius: 24px; font-size: 14px; font-weight: 600; cursor: pointer;
    transition: background 0.2s;
  }
  .chat-input button:hover:not(:disabled) { background: #1a3a6b; }
  .chat-input button:disabled { opacity: 0.5; cursor: not-allowed; }
  #start-screen {
    flex: 1; display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 40px; text-align: center; background: #f8fafc;
  }
  #start-screen h2 { font-size: 22px; color: #10264a; margin-bottom: 8px; }
  #start-screen p { color: #64748b; margin-bottom: 24px; font-size: 14px; line-height: 1.6; }
  #start-btn {
    padding: 14px 36px; background: #10264a; color: #fff; border: none;
    border-radius: 28px; font-size: 16px; font-weight: 600; cursor: pointer;
    transition: transform 0.2s, box-shadow 0.2s;
  }
  #start-btn:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(16,38,74,0.3); }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-6px); } }
  .hidden { display: none !important; }
</style>
</head>
<body>
<div class="chat-container">
  <div class="chat-header">
    <h1>Stability360 Thrive@Work</h1>
    <p>Powered by Trident United Way</p>
  </div>

  <div id="start-screen">
    <h2>Welcome!</h2>
    <p>Get help with Thrive@Work programs, check your eligibility,
       find community resources, or connect with a specialist.</p>
    <button id="start-btn" onclick="startChat()">Start Chat</button>
  </div>

  <div id="chat-area" class="hidden">
    <div class="chat-messages" id="messages"></div>
    <div class="chat-input">
      <input type="text" id="msg-input" placeholder="Type your message..."
             onkeydown="if(event.key==='Enter')sendMessage()" disabled>
      <button id="send-btn" onclick="sendMessage()" disabled>Send</button>
    </div>
  </div>
</div>

<script>
const LAMBDA_URL = window.location.origin;
let ws = null;
let connectionToken = null;
let chatActive = false;

function addMessage(text, type) {
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg ' + type;
  // Convert markdown-style bold and newlines
  let html = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\n/g, '<br>');
  div.innerHTML = html;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

function showTyping() {
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'typing';
  div.id = 'typing-indicator';
  div.innerHTML = '<span></span><span></span><span></span>';
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
}

function hideTyping() {
  const t = document.getElementById('typing-indicator');
  if (t) t.remove();
}

async function startChat() {
  document.getElementById('start-btn').textContent = 'Connecting...';
  document.getElementById('start-btn').disabled = true;

  try {
    const resp = await fetch(LAMBDA_URL + '/start-chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({displayName: 'Customer'}),
    });
    const data = await resp.json();

    if (!data.participantToken) throw new Error('No participant token');

    // Create participant connection
    const participant = await createParticipantConnection(data.participantToken, data.region);
    connectionToken = participant.connectionToken;

    // Connect WebSocket
    connectWebSocket(participant.websocketUrl);

    // Switch to chat view
    document.getElementById('start-screen').classList.add('hidden');
    document.getElementById('chat-area').classList.remove('hidden');
    document.getElementById('chat-area').style.display = 'flex';
    document.getElementById('chat-area').style.flexDirection = 'column';
    document.getElementById('chat-area').style.flex = '1';

    chatActive = true;
    document.getElementById('msg-input').disabled = false;
    document.getElementById('send-btn').disabled = false;
    document.getElementById('msg-input').focus();

  } catch (err) {
    console.error('Start chat error:', err);
    addMessage('Failed to connect. Please try again.', 'system');
    document.getElementById('start-btn').textContent = 'Start Chat';
    document.getElementById('start-btn').disabled = false;
  }
}

async function createParticipantConnection(participantToken, region) {
  const endpoint = `https://participant.connect.${region}.amazonaws.com`;
  const resp = await fetch(endpoint + '/participant/connection', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Amz-Bearer': participantToken,
    },
    body: JSON.stringify({
      Type: ['WEBSOCKET', 'CONNECTION_CREDENTIALS'],
    }),
  });
  const data = await resp.json();
  return {
    connectionToken: data.ConnectionCredentials.ConnectionToken,
    websocketUrl: data.Websocket.Url,
  };
}

function connectWebSocket(url) {
  ws = new WebSocket(url);

  ws.onopen = () => {
    console.log('WebSocket connected');
    // Subscribe to topics
    ws.send(JSON.stringify({
      topic: 'aws/subscribe',
      content: {
        topics: ['aws/chat']
      }
    }));
  };

  ws.onmessage = (event) => {
    try {
      const wrapper = JSON.parse(event.data);
      if (wrapper.topic === 'aws/chat') {
        const msg = JSON.parse(wrapper.content);
        handleChatEvent(msg);
      }
    } catch (e) {
      console.log('WS parse error:', e);
    }
  };

  ws.onclose = () => {
    console.log('WebSocket closed');
    if (chatActive) {
      chatActive = false;
      hideTyping();
      addMessage('Chat session ended.', 'system');
      document.getElementById('msg-input').disabled = true;
      document.getElementById('send-btn').disabled = true;
    }
  };

  ws.onerror = (err) => {
    console.error('WebSocket error:', err);
  };
}

function handleChatEvent(msg) {
  const type = msg.Type || msg.ContentType;
  const participant = msg.ParticipantRole || msg.Participant;
  const content = msg.Content || msg.Message || '';

  if (type === 'application/vnd.amazonaws.connect.event.typing') {
    if (participant !== 'CUSTOMER') showTyping();
    return;
  }

  if (type === 'application/vnd.amazonaws.connect.event.participant.joined') {
    return; // Ignore join events
  }

  if (type === 'application/vnd.amazonaws.connect.event.participant.left') {
    return;
  }

  if (type === 'application/vnd.amazonaws.connect.event.chat.ended') {
    chatActive = false;
    hideTyping();
    addMessage('Chat session ended. Refresh to start a new chat.', 'system');
    document.getElementById('msg-input').disabled = true;
    document.getElementById('send-btn').disabled = true;
    return;
  }

  // Text messages
  if (type === 'text/plain' || type === 'text/markdown') {
    hideTyping();
    if (participant === 'CUSTOMER') {
      // Our own message — already shown
    } else if (participant === 'SYSTEM') {
      if (content && content.trim()) addMessage(content, 'system');
    } else {
      // AGENT or BOT
      if (content && content.trim()) addMessage(content, 'bot');
    }
  }
}

async function sendMessage() {
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text || !chatActive || !connectionToken) return;

  input.value = '';
  addMessage(text, 'user');
  showTyping();

  const region = """ + f"'{REGION}'" + r""";
  const endpoint = `https://participant.connect.${region}.amazonaws.com`;

  try {
    await fetch(endpoint + '/participant/message', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Amz-Bearer': connectionToken,
      },
      body: JSON.stringify({
        ContentType: 'text/plain',
        Content: text,
      }),
    });
  } catch (err) {
    console.error('Send error:', err);
    hideTyping();
    addMessage('Failed to send message. Please try again.', 'system');
  }
}
</script>
</body>
</html>"""
