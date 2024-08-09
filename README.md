# Andromeda

## Overview

**Andromeda** is a social media web application where users can share pictures and videos, and chat with their family and friends. This project is built using Django for the backend, Angular for the frontend, Neo4j for the graph database, and Redis for caching and session management.

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
- **Neo4j**: Graph database management
- **Redis**: In-memory data structure store for caching and sessions
- **Docker**: Containerization of services
- **RESTful API**: Communication between frontend and backend
- **JWT Authentication**: Secure user authentication

## Prerequisites

- **Python 3.8+**
- **Node.js 12+ and npm**
- **Angular CLI**
- **Neo4j**
- **Redis**
- **Django 3.0+**
- **Docker**

## Getting Started

### Backend Setup

1. **Clone the repository**:
    ```bash
    git clone https://github.com/7irelo/andromeda-web.git
    cd andromeda-web
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

4. **Setup Neo4j and Redis**:
    - Make sure Neo4j and Redis are installed and running.
    - Update the `DATABASES` and `CACHES` settings in `server/settings.py` with your Neo4j and Redis credentials.

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

### Running the Application with Docker

1. **Build and start services with Docker**:
    ```bash
    docker-compose up --build
    ```

2. **Access the application**:
    - The Angular frontend will be available at `http://localhost:4200`.
    - The Django backend will run at `http://localhost:8000`.

## Project Structure

```
andromeda/
├── server/
│   ├── app/
│   ├── friends/
│   ├── marketplace/
│   ├── messages/
│   ├── notifications/
│   ├── posts/
│   ├── server/
│   ├── watch/
│   └── manage.py
└── client/
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
