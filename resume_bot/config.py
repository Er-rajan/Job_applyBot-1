# Resume Bot Configuration

CONFIG = {
    # Personal Info
    "name": "Rajan Gupta",
    "email": "rraajjaann2001@gmail.com",
    "phone": "8081421524",

    # Job Preferences
    "job_titles": [
        "Python Developer",
        "Software Engineer",
        "Backend Developer",
        "Full Stack Developer",
        "Machine Learning Engineer",
        "Artificial Intelligence Engineer",
        "Data Scientist",
        "Data Analyst",
        "DevOps Engineer",
        "Cloud Engineer",
        "SDE",
        "Computer Vision Engineer",
    ],
    "locations": ["Delhi", "Mumbai", "Bangalore", "Remote"],
    "experience_years": "Fresher",
    "expected_salary": "3.5 LPA",
    "requirement_keywords": [
        "nlp",
        "computer vision",
        "git",
        "linux",
        "data science",
        "ai",
        "gen ai",
        "deep learning",
        "backend",
        "yolo",
        "cnn",
        "ml",
        "image processing",
        "algorithms",
        "prediction modelling",
        "tensorflow",
        "pandas",
        "numpy",
        "scikit-learn",
        "pattern recognition",
        "mysql",
        "c++",
        "aws",
        "google cloud",
        "llm api integration",
        "devops",
        "oops",
        "agentic ai",
        "data analysis",
        "data visualization",
    ],
    "min_keyword_matches": 1,
    "max_external_links_per_job": 2,
    "application_profile": {
        "current_company": "Oplus Cowork",
        "current_job_title": "Robotics and AI Intern",
        "employment_status": "Currently Working",
        "qualification": "B.Tech",
        "specialization": "Computer Science and Engineering",
        "education": "B.Tech in Computer Science and Engineering",
        "cgpa": "7.0",
        "college": "Dr A. P. J. Abdul Kalam Technical University",
        "university": "Dr A. P. J. Abdul Kalam Technical University",
        "tenth_percentage": "73",
        "twelfth_percentage": "68",
        "source": "LinkedIn",
        "location": "Noida",
        "graduation_year": "2025",
        "notice_period_days": "7 days",
        "github_url": "https://github.com/Er-rajan",
        "linkedin_url": "https://www.linkedin.com/in/mr-rajan-86a039242",
        "email": "rraajjaann2001@gmail.com",
    },

    # Resume file path (relative to project root or absolute)
    "resume_path": "data/my_resume.pdf",
    "browser": {
        # engine: chromium/firefox/webkit (chrome, edge, brave use chromium engine)
        "engine": "chromium",
        # channel options with chromium engine: chrome, msedge, chromium
        # leave empty when using executable_path (for Brave/custom browser)
        "channel": "chrome",
        # for Brave set full binary path, e.g. /usr/bin/brave-browser
        "executable_path": "",
    },

    # Platform Credentials
    "platforms": {
        "naukri": {
            "enabled": True,
            "email": "rraajjaann2001@gmail.com",
            "password": "Rajan123@#",
        },
        "indeed": {
            "enabled": True,
            "email": "rraajjaann2001@gmail.com",
            "password": "Rajan123@#",
        },
        "internshala": {
            "enabled": True,
            "email": "rraajjaann2001@gmail.com",
            "password": "Rajan123@#",
        },
        "apna": {
            "enabled": True,
            "phone": "8081421524",
        },
    },

    # Runtime Settings
    "max_applications_per_day": 30,
    "delay_between_actions": 4,
    "delay_jitter_min": 0.8,
    "delay_jitter_max": 2.2,
    "otp_wait_seconds": 120,
    "headless": False,
}
