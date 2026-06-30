# SkillStamp

A skill verification and job matching platform for job seekers and recruiters.

## Features
- Add and manage skills
- Upload and verify certificates
- Browse and apply for jobs
- Post jobs and review applications

## Tech Stack
- Python, Flask
- MySQL
- HTML, CSS, JavaScript

## Quick Start
1. Clone repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/SkillStamp.git
   cd SkillStamp
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Setup MySQL database `skillstamp` and update credentials in `app.py`.
4. Run app:
   ```bash
   python app.py
   ```
5. Open `http://localhost:5000`

## Project Structure
- `app.py` – Flask application
- `requirements.txt` – dependencies
- `static/style.css` – styles
- `templates/` – HTML pages
- `uploads/` – certificate files

## Database Tables
- `user`
- `skill`
- `certificate`
- `job_posting`
- `application`

## Notes
- Uploads support PDF, JPG, PNG
- Max file size: 16MB
- Passwords are hashed with Werkzeug
- Uses session-based login

---

**Built for connecting talent with opportunity**
