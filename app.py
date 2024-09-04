import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, firestore, storage
from openai import OpenAI
from datetime import datetime
import pytz
import json
import csv
import time
import threading

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["FIREBASE"]))
    firebase_admin.initialize_app(cred, {
        'storageBucket': st.secrets["FIREBASE"]["storage_bucket"]
    })

# Initialize Firestore DB
db = firestore.client()

# Get London timezone
london_tz = pytz.timezone("Europe/London")

# Function to add timestamp in London time
def add_timestamp(message):
    now_london = datetime.now(pytz.utc).astimezone(london_tz)
    message['timestamp'] = now_london.strftime("%Y-%m-%d %H:%M:%S")
    message['length'] = len(message['content'].split())  # Count the number of words
    return message

# Function to calculate response time between messages
def calculate_response_time(messages):
    for i in range(1, len(messages)):
        current_time = datetime.strptime(messages[i]['timestamp'], "%Y-%m-%d %H:%M:%S")
        previous_time = datetime.strptime(messages[i-1]['timestamp'], "%Y-%m-%d %H:%M:%S")
        messages[i]['response_time'] = (current_time - previous_time).total_seconds()
    return messages

# Function to save chat log in CSV format
def save_chat_log():
    st.session_state["messages"] = calculate_response_time(
        [add_timestamp(msg) if 'timestamp' not in msg else msg for msg in st.session_state["messages"]]
    )
    
    # Prepare CSV file path
    user_email = st.session_state['user'].email.replace('@', '_').replace('.', '_')
    filename = f"{user_email}_{datetime.now(london_tz).strftime('%H%M')}_chat_log.csv"

    # Write to CSV
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['date', 'time', 'role', 'content', 'length', 'response_time']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for msg in st.session_state["messages"]:
            # Split timestamp into date and time
            date, time = msg['timestamp'].split(' ')
            writer.writerow({
                'date': date,
                'time': time,
                'role': msg['role'],
                'content': msg['content'],
                'length': msg['length'],
                'response_time': msg.get('response_time', '')
            })
    
    # Upload CSV file
    bucket = storage.bucket(st.secrets["FIREBASE"]["storage_bucket"])
    blob = bucket.blob(f"chat_logs/{st.session_state['user'].uid}_{filename}")
    blob.upload_from_filename(filename)
    blob.make_public()
    st.success(f"Chat log saved. Access it [here]({blob.public_url}).")

# Function to handle chat
def handle_chat(prompt):
    st.session_state["messages"].append(add_timestamp({"role": "user", "content": prompt}))
    st.chat_message("user").write(prompt)
    
    # Simulate AI response
    response = OpenAI(api_key=st.secrets["default"]["OPENAI_API_KEY"]).chat.completions.create(
        model="gpt-4o",
        messages=st.session_state["messages"],
        temperature=1,
        max_tokens=4095
    )
    st.session_state["messages"].append(add_timestamp({"role": "assistant", "content": response.choices[0].message.content}))
    st.chat_message("assistant").write(response.choices[0].message.content)
    
    save_chat_log()

# Login/Register logic
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user'] = None

if not st.session_state['logged_in']:
    st.title("Login / Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Register"):
        user = auth.create_user(email=email, password=password)
        st.session_state['logged_in'] = True
        st.session_state['user'] = user
    elif st.button("Login"):
        user = auth.get_user_by_email(email)
        st.session_state['logged_in'] = True
        st.session_state['user'] = user
    st.stop()

# Chat UI
st.title("💬 Essay Writing Assistant")
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        add_timestamp({"role": "system", "content": """
Role: Essay Writing Assistant (300-500 words)

Response Length : Elaborate your answers. Max. 200 words per responses.

Focus on questions and hints: Only ask guiding questions and provide hints to stimulate student writing.

Avoid full drafts: No complete paragraphs or essays will be provided.

Instructions:
1. Topic Selection: Begin by asking the student for their preferred topic or suggest 4-5 topics. Move forward only after a topic is chosen.

2. Outline Creation: Prompt the student to draft an outline (introduction, body paragraphs, conclusion) using guiding questions. Avoid giving examples/suggested structure.
    - Wait for Submission: Pause and wait for the student's draft.
    - Feedback and Confirmation: Provide feedback on their outline, suggest revisions, and confirm the final version before proceeding to the essay draft.

3. Drafting: After outline approval, prompt the student to draft the introduction using up to 3 guiding question. Pause and wait for their draft submission.

4. Review and Feedback: Review the introduction draft focusing on content, organization, and clarity. Offer up to 3 feedbacks. Pause and wait for the revised draft; avoid providing a refined version.

5. Final Review: On receiving the revised draft, assist in proofreading for grammar, punctuation, and spelling. identifying up to 3 issues for the introduction. Pause and await the final draft; avoid providing a refined version.

6. Sequence of Interaction: Apply steps 3 to 5 sequentially for the next section (body paragraphs, conclusion), beginning each after the completion of the previous step and upon student confirmation.

7. Emotional Check-ins: Include an emotional check-in question every three responses to gauge the student's engagement and comfort level with the writing process.

Additional Guidelines:
• Partial Responses: Provide only snippets or partial responses to guide the student in writing their essay.
• Interactive Assistance: Engage the student in an interactive manner, encouraging them to think and write independently.
• Clarifications: Always ask for clarification if the student's request is unclear to avoid giving a complete essay response
        """}),
        add_timestamp({"role": "assistant", "content": "Hi there! Ready to start your essay? I'm here to guide and help you improve your essay writing skills with activities like:\n"
               "1. **Topic Selection**\n"
               "2. **Outlining**\n"
               "3. **Drafting**\n"
               "4. **Reviewing**\n"
               "5. **Proofreading**\n\n"
               "What topic are you interested in writing about? If you'd like suggestions, just let me know!"
                    })
    ]
    save_chat_log()

# Display chat messages, excluding the system prompt
for msg in st.session_state["messages"]:
    if msg["role"] != "system":
        st.chat_message(msg["role"]).write(f"[{msg['timestamp']}] {msg['content']}")

if prompt := st.chat_input():
    handle_chat(prompt)

# Function to keep the session alive
def keep_alive():
    while st.session_state['logged_in']:
        # Send a keep-alive signal or perform a lightweight action
        st.write("Keeping session alive...")
        time.sleep(60)  # Wait for 60 seconds (1 minute)

# Start the keep-alive process in a separate thread
if st.session_state['logged_in']:
    threading.Thread(target=keep_alive, daemon=True).start()

