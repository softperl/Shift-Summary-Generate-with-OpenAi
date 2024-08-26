
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Email, Length
from flask_mail import Mail, Message
import jwt
import datetime
import logging
from openai import OpenAI
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = '75#Trd6mhu'  # Replace with your actual secret key

# Configure MySQL
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'toortoor'
app.config['MYSQL_DB'] = 'carelogix'
app.config['MYSQL_HOST'] = 'localhost'
mysql = MySQL(app)

# Configure Flask-Mail
app.config['MAIL_SERVER'] = 'sandbox.smtp.mailtrap.io'  # Replace with your SMTP server
app.config['MAIL_PORT'] = 2525
app.config['MAIL_USERNAME'] = '96ae120e742949'
app.config['MAIL_PASSWORD'] = '9b0c2686635c64'
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

# Configure OpenAI
client = OpenAI(api_key="sk-k19opYJHI2tCUPzi6XQp8dspTjHHPlJ-PVcIlj-vjGT3BlbkFJfsPuNTWlMWV1qJciwgCvP4J8j4yPCurxQvBno-bVIA")

logging.basicConfig(level=logging.DEBUG)

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[InputRequired(), Email()])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=6)])
    submit = SubmitField('Login')

class SignupForm(FlaskForm):
    name = StringField('Name', validators=[InputRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[InputRequired(), Email()])
    password = PasswordField('Password', validators=[InputRequired(), Length(min=6)])
    submit = SubmitField('Sign Up')

def send_verification_email(email, token):
    verification_link = url_for('verify_email', token=token, _external=True)
    msg = Message('Please Verify Your Email Address',
                  sender='your-email@example.com',
                  recipients=[email])
    msg.html = render_template('email_verification.html', verification_link=verification_link)
    mail.send(msg)

def generate_summary(client_name, shift_duration, total_hours, total_minutes, questions, answers):
    input_text = (
        f"Client Name: {client_name}\n"
        f"Shift Duration: {shift_duration}\n"
        f"Total Hours: {total_hours:02}:{total_minutes:02}\n\n"
        f"Questions and Answers:\n"
    )

    for q, a in zip(questions, answers):
        input_text += f"Question: {q}\nAnswer: {a}\n\n"

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant tasked with creating a detailed shift summary for a client. "
                    "Based on the provided data, generate a comprehensive and narrative-style summary of the client's shift. "
                    "The summary should flow chronologically through the shift, providing specific details about events, "
                    "behaviors, and interactions. Include timestamps where appropriate. Be sure to mention:\n"
                    "1. Specific activities the client engaged in\n"
                    "2. Any behavioral issues or notable incidents\n"
                    "3. Interactions with staff or other individuals\n"
                    "4. Any changes in mood or behavior throughout the shift\n"
                    "5. Details about meals, medications, or personal care\n"
                    "6. Any unusual or unexpected events\n"
                    "7. Total hours of the shift in HH:MM format\n\n"
                    "After the narrative summary, provide a brief overview of key points and any recommendations for future shifts. "
                    "Ensure all information is directly derived from the provided data and maintain a professional tone."
                )
            },
            {
                "role": "user",
                "content": f"Here's the shift data:\n\n{input_text}\n\nPlease provide a detailed narrative summary of the shift."
            }
        ],
        max_tokens=2000,
        n=1,
        stop=None,
        temperature=0.7
    )

    if response.choices:
        summary = response.choices[0].message.content.strip()
    else:
        summary = "No summary generated."

    return summary


def generate_questions(start_time, end_time):
    questions = []

    current_time = start_time
    while current_time < end_time:
        next_hour = (current_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        if next_hour > end_time:
            next_hour = end_time

        time_range = f"{current_time.strftime('%I:%M %p')} to {next_hour.strftime('%I:%M %p')}"
        questions.extend([
            f"What did the client do from {time_range}?",
            f"Were there any notable behaviors from {time_range}? If so, please describe them.",
            f"Quantify any notable behaviors from {time_range}. For example, 'hit his head 10 times' or 'pulled staff 3 times'."
        ])

        current_time = next_hour

    return questions

def send_reset_email(email, reset_link):
    msg = Message('Password Reset Request',
                  sender='your-email@example.com',
                  recipients=[email])
    msg.html = render_template('reset_email.html', reset_link=reset_link)
    mail.send(msg)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        password = generate_password_hash(form.password.data)
        token = jwt.encode({'email': email, 'exp': datetime.utcnow() + timedelta(hours=1)},
                            app.secret_key, algorithm='HS256')

        conn = mysql.connection
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('Email already exists. Please choose a different email.', 'danger')
        else:
            cursor.execute("INSERT INTO users (name, email, password, verified) VALUES (%s, %s, %s, %s)", 
                           (name, email, password, False))
            conn.commit()
            cursor.close()
            send_verification_email(email, token)
            flash('Account created successfully! Please check your email to verify your account.', 'success')
            return redirect(url_for('login'))
    
    return render_template('signup.html', form=form)

@app.route('/verify/<token>')
def verify_email(token):
    try:
        data = jwt.decode(token, app.secret_key, algorithms=['HS256'])
        email = data['email']
    except:
        flash('The verification link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))

    conn = mysql.connection
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET verified = 1 WHERE email = %s", (email,))
    conn.commit()
    cursor.close()

    flash('Your email has been verified successfully!', 'success')
    return redirect(url_for('login'))

from datetime import datetime, timedelta  # Make sure to import datetime and timedelta


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        conn = mysql.connection
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        
        if user:
            user_id = user[0]
            token = jwt.encode(
                {'reset_password': user_id, 'exp': datetime.utcnow() + timedelta(hours=1)},
                app.secret_key,
                algorithm='HS256'
            )
            reset_link = url_for('reset_password', token=token, _external=True)
            
            # Save token and expiry in the database
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET reset_token = %s, reset_token_expiry = %s WHERE id = %s", 
                           (token, datetime.utcnow() + timedelta(hours=1), user_id))
            conn.commit()
            cursor.close()

            send_reset_email(email, reset_link)
            flash('A password reset link has been sent to your email.', 'info')
            return redirect(url_for('login'))
        else:
            flash('Email address not found.', 'danger')

    return render_template('forgot_password.html')


def send_reset_email(email, reset_link):
    msg = Message('Password Reset Request',
                  sender='your-email@example.com',
                  recipients=[email])
    msg.html = render_template('reset_email.html', reset_link=reset_link)
    mail.send(msg)
  
  
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        data = jwt.decode(token, app.secret_key, algorithms=['HS256'])
        user_id = data['reset_password']
        
        conn = mysql.connection
        cursor = conn.cursor()
        cursor.execute("SELECT reset_token, reset_token_expiry FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user or user[0] != token or datetime.utcnow() > user[1]:
            flash('The reset link is invalid or has expired.', 'danger')
            return redirect(url_for('forgot_password'))

        if request.method == 'POST':
            new_password = request.form.get('password')
            hashed_password = generate_password_hash(new_password)
            
            cursor.execute("UPDATE users SET password = %s, reset_token = NULL, reset_token_expiry = NULL WHERE id = %s", 
                           (hashed_password, user_id))
            conn.commit()
            cursor.close()
            
            flash('Your password has been updated!', 'success')
            return redirect(url_for('login'))
        
    except jwt.ExpiredSignatureError:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('forgot_password'))
    except Exception as e:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('forgot_password'))

    return render_template('reset_password.html', token=token)

@app.route('/policy', methods=['GET', 'POST'])
def policy():
    user_id = session.get('user_id')

    if request.method == 'POST':
        if user_id:
            action = request.form.get('action')
            conn = mysql.connection
            cursor = conn.cursor()

            if action == 'accept':
                cursor.execute("UPDATE users SET policy_accepted = 1 WHERE id = %s", (user_id,))
                conn.commit()
                return redirect(url_for('dashboard'))
            elif action == 'reject':
                flash('You must accept the policy to use the application.', 'danger')
                return redirect(url_for('logout'))
        else:
            flash('You need to be logged in to accept or reject the policy.', 'danger')
            return redirect(url_for('login'))

    return render_template('policy.html', logged_in=user_id is not None)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        conn = mysql.connection
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user[3], password):
            if user[4]:  # Check if the user is verified
                session['user_id'] = user[0]

                # Check if the policy has been accepted
                if not user[7]:  # Assuming policy_accepted is the 8th column
                    return redirect(url_for('policy'))

                return redirect(url_for('dashboard'))
            else:
                flash('Please verify your email address before logging in.', 'danger')
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))


@app.route('/resume_shift/<shift_id>', methods=['GET'])
def resume_shift(shift_id):
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))

    conn = mysql.connection
    cursor = conn.cursor()

    # Fetch the last answered question index
    cursor.execute("SELECT current_question FROM user_progress WHERE user_id = %s AND shift_id = %s", 
                   (session['user_id'], shift_id))
    progress = cursor.fetchone()

    if not progress:
        flash("Progress not found.", "danger")
        return redirect(url_for('dashboard'))

    # Get the current question index
    current_question_index = progress[0]

    # Fetch all questions for the shift
    cursor.execute("SELECT id, is_answered FROM question_answers WHERE shift_id = %s ORDER BY id ASC", (shift_id,))
    questions = cursor.fetchall()

    # Find the next unanswered question or handle the case when all questions are answered
    total_questions = len(questions)
    while current_question_index < total_questions:
        question_id, is_answered = questions[current_question_index]

        if not is_answered:  # If the current question is not answered
            break
        
        current_question_index += 1

    # If we have reached the end of the list and all questions were answered
    if current_question_index >= total_questions:
        # All questions are answered; you can handle this case if needed
        flash("All questions are answered. Returning to dashboard.", "info")
        return redirect(url_for('dashboard'))

    # Store in session
    session[f'resume_shift_id'] = shift_id
    session[f'resume_current_question_{shift_id}'] = current_question_index

    return redirect(url_for('questions', shift_id=shift_id))



@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))

    hours = range(1, 13)
    minutes = [f"{m:02d}" for m in [0, 15, 30, 45]]
    periods = ['AM', 'PM']

    conn = mysql.connection
    cursor = conn.cursor()

    if request.method == 'POST':
        # Existing code for generating summary...

        # Save shift data to database
        client_name = request.form['client_name'].strip()
        start_hour = int(request.form['start_hour'].strip())
        start_minute = int(request.form['start_minute'].strip())
        start_period = request.form['start_period'].strip()
        end_hour = int(request.form['end_hour'].strip())
        end_minute = int(request.form['end_minute'].strip())
        end_period = request.form['end_period'].strip()

        start_time_str = f"{start_hour}:{start_minute:02d} {start_period}"
        end_time_str = f"{end_hour}:{end_minute:02d} {end_period}"

        try:
            shift_start = datetime.strptime(start_time_str, "%I:%M %p")
            shift_end = datetime.strptime(end_time_str, "%I:%M %p")
        except ValueError as e:
            flash(f"Error parsing time: {e}", "danger")
            return redirect(url_for('dashboard'))

        if shift_end < shift_start:
            shift_end += timedelta(days=1)

        if shift_start != shift_end:
            shift_duration = f"{shift_start.strftime('%I:%M %p')} to {shift_end.strftime('%I:%M %p')}"
            total_duration = shift_end - shift_start
            total_hours = total_duration.seconds // 3600
            total_minutes = (total_duration.seconds % 3600) // 60

            cursor.execute("INSERT INTO shifts (client_name, shift_duration, total_hours, total_minutes, user_id, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                           (client_name, shift_duration, total_hours, total_minutes, session['user_id'], datetime.utcnow()))
            shift_id = cursor.lastrowid
            conn.commit()

            questions = generate_questions(shift_start, shift_end)

            # Save questions to database
            cursor.execute("DELETE FROM question_answers WHERE shift_id = %s", (shift_id,))
            for question in questions:
                cursor.execute("INSERT INTO question_answers (shift_id, question, answer) VALUES (%s, %s, %s)", (shift_id, question, None))
            conn.commit()

            # Create an entry for user progress
            cursor.execute("INSERT INTO user_progress (user_id, shift_id, current_question) VALUES (%s, %s, %s)",
                           (session['user_id'], shift_id, 0))
            conn.commit()
            cursor.close()

            return redirect(url_for('questions', shift_id=shift_id))
        else:
            flash("Start time and end time cannot be the same. Please enter valid times.", "danger")

    # Fetch saved progress
    cursor.execute("""
        SELECT s.id, s.client_name, s.shift_duration, s.created_at
        FROM shifts s
        JOIN user_progress up ON s.id = up.shift_id
        WHERE up.user_id = %s
    """, (session['user_id'],))
    saved_progress = cursor.fetchall()
    cursor.close()

    return render_template('dashboard.html', hours=hours, minutes=minutes, periods=periods, saved_progress=saved_progress)

@app.route('/questions/<int:shift_id>', methods=['GET', 'POST'])
def questions(shift_id):
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))

    conn = mysql.connection
    cursor = conn.cursor()

    # Fetch shift details
    cursor.execute("SELECT client_name, shift_duration, total_hours, total_minutes FROM shifts WHERE id = %s", (shift_id,))
    shift_details = cursor.fetchone()

    if not shift_details:
        flash("Shift details not found.", "danger")
        return redirect(url_for('dashboard'))

    # Fetch questions for the current shift
    cursor.execute("SELECT id, question, is_answered FROM question_answers WHERE shift_id = %s ORDER BY id ASC", (shift_id,))
    questions = cursor.fetchall()
    total_questions = len(questions)

    if total_questions == 0:
        flash("No questions found for this shift.", "danger")
        return redirect(url_for('dashboard'))

    # Determine the current question index
    current_question_index = session.get(f'resume_current_question_{shift_id}', 0)

    if request.method == 'POST':
        action = request.form.get('action')
        answer = request.form.get('answer', '').strip()

        # Save the answer for the current question
        if answer:
            question_id = questions[current_question_index][0]
            cursor.execute("UPDATE question_answers SET answer = %s, is_answered = TRUE WHERE id = %s AND shift_id = %s", (answer, question_id, shift_id))
            conn.commit()

        if action == 'save':
            cursor.execute("UPDATE user_progress SET current_question = %s WHERE user_id = %s AND shift_id = %s",
                           (current_question_index, session['user_id'], shift_id))
            conn.commit()
            cursor.close()
            flash('Progress saved successfully.', 'success')
            return redirect(url_for('dashboard'))

        elif action == 'next':
            # Save current question progress
            cursor.execute("UPDATE user_progress SET current_question = %s WHERE user_id = %s AND shift_id = %s",
                           (current_question_index, session['user_id'], shift_id))
            conn.commit()

            # Move to the next unanswered question
            while current_question_index < total_questions:
                current_question_index += 1
                if current_question_index >= total_questions:
                    break
                
                question_id = questions[current_question_index][0]
                cursor.execute("SELECT is_answered FROM question_answers WHERE id = %s AND shift_id = %s", (question_id, shift_id))
                is_answered = cursor.fetchone()

                if not is_answered or not is_answered[0]:  # Check if not answered
                    break

            if current_question_index >= total_questions:
                cursor.execute("DELETE FROM user_progress WHERE user_id = %s AND shift_id = %s", (session['user_id'], shift_id))
                conn.commit()

                cursor.execute("SELECT question, answer FROM question_answers WHERE shift_id = %s", (shift_id,))
                questions_and_answers = cursor.fetchall()

                questions = [qa[0] for qa in questions_and_answers]
                answers = [qa[1] for qa in questions_and_answers]

                # Check if summary already exists
                cursor.execute("SELECT summary FROM shifts WHERE id = %s", (shift_id,))
                existing_summary = cursor.fetchone()

                if not existing_summary[0]:
                    summary = generate_summary(
                        client_name=shift_details[0],
                        shift_duration=shift_details[1],
                        total_hours=shift_details[2],
                        total_minutes=shift_details[3],
                        questions=questions,
                        answers=answers
                    )

                    # Save summary to database
                    cursor.execute("UPDATE shifts SET summary = %s WHERE id = %s", (summary, shift_id))
                    conn.commit()

                else:
                    summary = existing_summary[0]

                return render_template('summary.html', summary=summary)

            session[f'resume_current_question_{shift_id}'] = current_question_index

        elif action == 'previous':
            if current_question_index > 0:
                current_question_index -= 1

            session[f'resume_current_question_{shift_id}'] = current_question_index

        elif action == 'finish':
            # Save the final answer
            if answer:
                question_id = questions[current_question_index][0]
                cursor.execute("UPDATE question_answers SET answer = %s, is_answered = TRUE WHERE id = %s AND shift_id = %s", (answer, question_id, shift_id))
                conn.commit()

            cursor.execute("DELETE FROM user_progress WHERE user_id = %s AND shift_id = %s", (session['user_id'], shift_id))
            conn.commit()

            cursor.execute("SELECT question, answer FROM question_answers WHERE shift_id = %s", (shift_id,))
            questions_and_answers = cursor.fetchall()

            questions = [qa[0] for qa in questions_and_answers]
            answers = [qa[1] for qa in questions_and_answers]

            # Check if summary already exists
            cursor.execute("SELECT summary FROM shifts WHERE id = %s", (shift_id,))
            existing_summary = cursor.fetchone()

            if not existing_summary[0]:
                summary = generate_summary(
                    client_name=shift_details[0],
                    shift_duration=shift_details[1],
                    total_hours=shift_details[2],
                    total_minutes=shift_details[3],
                    questions=questions,
                    answers=answers
                )

                # Save summary to database
                cursor.execute("UPDATE shifts SET summary = %s WHERE id = %s", (summary, shift_id))
                conn.commit()

            else:
                summary = existing_summary[0]

            return render_template('summary.html', summary=summary)

    # Fetch the answer for the current question
    current_question_id = questions[current_question_index][0] if questions else None
    if current_question_id:
        cursor.execute("SELECT answer FROM question_answers WHERE id = %s AND shift_id = %s", (current_question_id, shift_id))
        result = cursor.fetchone()
        answer = result[0] if result and result[0] is not None else ''
    else:
        answer = ''

    cursor.close()
    question_text = questions[current_question_index][1] if questions else 'No more questions'
    return render_template('questions.html', question=question_text, answer=answer, current_question=current_question_index, total_questions=total_questions, questions=questions, shift_id=shift_id)

@app.route('/summary')
def summary():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))

    conn = mysql.connection
    cursor = conn.cursor()

    # Fetch the current shift and its details
    cursor.execute("SELECT shift_id, client_name, shift_duration, total_hours, total_minutes FROM shifts WHERE user_id = %s ORDER BY id DESC LIMIT 1", (session['user_id'],))
    shift_data = cursor.fetchone()

    if not shift_data:
        flash("No completed shift found.", "danger")
        return redirect(url_for('dashboard'))

    shift_id = shift_data[0]

    # Fetch the summary for the shift
    cursor.execute("SELECT summary FROM shifts WHERE id = %s", (shift_id,))
    summary_data = cursor.fetchone()

    if not summary_data or not summary_data[0]:
        flash("Summary not found. Please complete the shift questions first.", "danger")
        return redirect(url_for('dashboard'))

    summary = summary_data[0]

    cursor.close()
    return render_template('summary.html', summary=summary)


if __name__ == '__main__':
    app.run(debug=True)
