# Resume Bot Configuration

CONFIG = {
    # Personal Info
    "name": "Your Name",
    "email": "you@example.com",
    "phone": "9876543210",

    # Job Preferences
    "job_titles": [
        "Python Developer",
        "Software Engineer",
        "Backend Developer",
        "Full Stack Developer",
    ],
    "locations": ["Delhi", "Mumbai", "Bangalore", "Remote"],
    "experience_years": 2,
    "expected_salary": "8 LPA",

    # Resume file path (relative to project root or absolute)
    "resume_path": "data/my_resume.pdf",

    # Platform Credentials
    "platforms": {
        "naukri": {
            "enabled": True,
            "email": "you@example.com",
            "password": "your_naukri_password",
        },
        "indeed": {
            "enabled": True,
            "email": "you@example.com",
            "password": "your_indeed_password",
        },
        "internshala": {
            "enabled": True,
            "email": "you@example.com",
            "password": "your_internshala_password",
        },
        "apna": {
            "enabled": True,
            "phone": "9876543210",
        },
    },

    # Runtime Settings
    "max_applications_per_day": 20,
    "delay_between_actions": 2,
    "headless": False,
}
