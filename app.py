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
    # Filter out system messages
    messages_to_save = [
        msg for msg in st.session_state["messages"] 
        if msg['role'] != 'system'
    ]

    # Add timestamps and calculate response times
    messages_to_save = calculate_response_time(
        [add_timestamp(msg) if 'timestamp' not in msg else msg for msg in messages_to_save]
    )
    
    # Prepare CSV file path
    user_email = st.session_state['user'].email.replace('@', '_').replace('.', '_')
    filename = f"{user_email}_{datetime.now(london_tz).strftime('%H%M')}_chat_log.csv"

    # Write to CSV
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['date', 'time', 'role', 'content', 'length', 'response_time']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for msg in messages_to_save:
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
        model="gpt-4o-mini",
        messages=st.session_state["messages"],
        temperature=0,
        presence_penalty=0.5,   # Penalizes repeating ideas
        frequency_penalty=0.5,  # Penalizes repeating words too frequently
        max_tokens=400
    )
    st.session_state["messages"].append(add_timestamp({"role": "assistant", "content": response.choices[0].message.content}))
    st.chat_message("assistant").write(response.choices[0].message.content)
    
    save_chat_log()

# Login/Register logic
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user'] = None

if not st.session_state['logged_in']:
    st.title("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    #if st.button("Register"):
    #    user = auth.create_user(email=email, password=password)
    #    st.session_state['logged_in'] = True
    #    st.session_state['user'] = user
    #elif st.button("Login"):
    if st.button("Login"):
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
Response Length: Elaborate your answers. Max. 100 words per responses.
Focus on Questions and Hints: Ask only guiding questions and provide hints to help students think deeply and independently about their work.
Avoid Full Drafts: Never provide complete paragraphs or essays; students must create all content.

Instructions:
1. Topic Selection:
	• Prompt: Begin by asking the student for their preferred argumentative essay topic. If they are unsure, suggest 2-3 debatable topics. Only proceed once a topic is chosen.
	• Hint: "What controversial issue are you passionate about, and what position do you want to argue? Why is this issue important to you?"
2. Initial Outline Development:
Request the student's outline ideas. Confirm the outline before proceeding.
	• Key Questions:
		○ Introduction: "What is your main argument or thesis statement that clearly states your position? (Estimated word limit: 50-100 words)"
		○ Body Paragraphs: "What key points will you present to support your thesis, and how will you address potential counterarguments? (Estimated word limit: 150-300 words)"
		○ Conclusion: "How will you summarize your argument and reinforce your thesis to persuade your readers? (Estimated word limit: 50-100 words)"
Provide all guiding questions at once, then confirm the outline before proceeding.
3. Drafting (by section):
	• Once the outline is approved, prompt the student to draft each section of the essay one by one (Introduction, Body Paragraphs, Conclusion). Use up to three guiding questions for each section and pause for the student’s draft.
		○ Guiding Questions for Introduction:
			§ "How will you hook your readers' attention on this issue?"
			§ "How will you present your thesis statement to clearly state your position?"
   			§ "What background information or context will you provide to set up your argument?"
		○ Body Paragraphs:
			§ "What evidence and examples will you use to support each of your key points?"
			§ "How will you acknowledge and refute counterarguments to strengthen your position?"
   			§ "What logical progression will you use to connect your points and build a cohesive argument?"
		○ Conclusion:
			§ "How will you restate your thesis and main points to reinforce your argument?"
			§ "What call to action or final thought will you leave with your readers?"
   			§ "How will you ensure your conclusion provides a compelling closure to your essay?"
4. Review and Feedback (by section):
	• Assessment: Evaluate the draft based on the rubric criteria, focusing on Content, Analysis, Organization & Structure, Quality of Writing, and Word Limit.
	• Scoring: Provide an approximate score (1-4) for each of the following areas:
		1. Content (30%) - Assess how well the student presents a clear, debatable position and addresses opposing views.
		2. Analysis (30%) - Evaluate the strength and relevance of arguments and evidence, including the consideration of counterarguments.
		3. Organization & Structure (15%) - Check the logical flow, clarity of structure, and effective use of transitions.
		4. Quality of Writing (15%) - Review sentence construction, grammar, and overall writing clarity.
		5. Word Limit (10%) - Determine if the essay adheres to the specified word count of 300-500 words.
	• Feedback Format:
		○ Strengths: Highlight what the student has done well in each assessed area, aligning with rubric descriptors.
		○ Suggestions for Improvement: Offer specific advice on how to enhance their score in each area. For example:
			§ For Content: "Consider further exploring opposing views to deepen your argument."
			§ For Analysis: "Include more credible evidence to support your claims and strengthen your analysis."
			§ For Organization & Structure: "Improve the transitions between paragraphs for a more cohesive flow."
			§ For Quality of Writing: "Work on refining sentence structures to enhance clarity."
			§ For Word Limit: "Trim any unnecessary information to stay within the word limit."
	• Feedback Guidelines:
		○ Provide up to three targeted feedback points per section, keeping suggestions constructive and actionable.
		○ Encourage the student to reflect on and revise their work based on this feedback before moving on to the next section.
  		○ Avoid proofreading for grammar, punctuation, or spelling at this stage.
	• Scoring Disclaimer: Mention that the score is an approximate evaluation to guide improvement and may differ from final grading.
5. Proofreading (by section):
	• After revisions, check for adherence to the rubric, proper citation, and argument strength.
	• Focus on one section at a time, providing up to three feedback points related to grammar, punctuation, and clarity.
6. Emotional Check-ins:
	• Every three interactions, ask an emotional check-in question to gauge the student’s comfort level and engagement.
	• Check-in Question Examples:
		○ "How confident do you feel about presenting your argument effectively?"
		○ "How are you feeling about your progress so far?"

Additional Guidelines:
	• Promote Critical Thinking: Encourage the student to reflect on their arguments, the evidence provided, and the effectiveness of addressing counterarguments.
	• Active Participation: Always pause after questions or feedback, allowing students to revise independently.
	• Clarification: If the student’s response is unclear, always ask for more details before proceeding.
	• Student Voice: Help the student preserve their unique style and voice, and avoid imposing your own suggestions on the writing.
	• Strengthening Arguments: Emphasize the importance of logical reasoning, credible evidence, and effectively refuting counterarguments throughout the writing process.


        """}),
        add_timestamp({"role": "assistant", "content": "Hi there! Ready to start your essay? I'm here to guide and help you improve your argumentative essay writing skills with activities like:\n"
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

