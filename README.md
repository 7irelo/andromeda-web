# Andromeda - Social Media Web Application

## Overview

**Andromeda** is a social media web application where users can share pictures and videos, and chat with their family and friends. This project is built using Django for the backend, Angular for the frontend, and MySQL for the database.

## Features

### User Features
- **User Registration and Authentication**
- **Profile Management**
- **Media Sharing (Photos and Videos)**
- **News Feed**
- **Likes, Comments, and Sharing**
- **Instant Messaging and Group Chats**
- **Notifications**
- **Search and Discovery**
- **Privacy and Security Settings**

### Technical Features
- **Django**: Backend framework
- **Angular**: Frontend framework
- **MySQL**: Database management
- **RESTful API**: Communication between frontend and backend
- **JWT Authentication**: Secure user authentication

## Prerequisites

- **Python 3.8+**
- **Node.js 12+ and npm**
- **Angular CLI**
- **MySQL 8+**
- **Django 3.0+**

## Getting Started

### Backend Setup

1. **Clone the repository**:
    ```bash
    git clone https://github.com/7irelo/andromeda.web.git
    cd andromeda.web
    ```

2. **Create a virtual environment and activate it**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. **Install the dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4. **Setup MySQL database**:
    - Create a new MySQL database named `andromeda`.
    - Update `DATABASES` settings in `server/settings.py` with your MySQL credentials.

5. **Apply migrations**:
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

6. **Create a superuser**:
    ```bash
    python manage.py createsuperuser
    ```

7. **Start the backend server**:
    ```bash
    python manage.py runserver
    ```

### Frontend Setup

1. **Navigate to the frontend directory**:
    ```bash
    cd frontend
    ```

2. **Install Angular dependencies**:
    ```bash
    npm install
    ```

3. **Start the Angular development server**:
    ```bash
    ng serve
    ```

### Running the Application

- Open your browser and go to `http://localhost:4200` to see the Angular frontend.
- The Django backend runs at `http://localhost:8000`.

## Project Structure

```
andromeda/
├── backend/
│   ├── andromeda/
│   ├── users/
│   ├── posts/
│   ├── chat/
│   └── manage.py
└── frontend/
    ├── src/
    ├── angular.json
    └── package.json
```

## Contributing

We welcome contributions from the community. Please follow these steps to contribute:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature-branch`).
3. Make your changes.
4. Commit your changes (`git commit -m 'Add some feature'`).
5. Push to the branch (`git push origin feature-branch`).
6. Open a pull request.

Please ensure your code adheres to the project's coding standards and includes appropriate tests.

## Issues and Bug Reports

If you encounter any issues or bugs, please report them on our [Issue Tracker](https://github.com/7irelo/andromeda.web/issues).

## License

This project is licensed under the [MIT License](LICENSE).

## Contact

For any queries or support, please contact us at support@andromeda-socialmedia.com.

---

Thank you for contributing to Andromeda! We hope this project helps you create a fantastic social media application.
