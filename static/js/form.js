import React from 'react';
import ReactDOM from 'react-dom';

class LoginForm extends React.Component {
    handleSubmit(event) {
        event.preventDefault();
        const form = event.target;

        fetch(form.action, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            },
            body: JSON.stringify({
                username: form.username.value,
                password: form.password.value,
            }),
        })
        .then(response => {
            if (response.ok) {
                Turbo.visit(response.url);  // Turbo.js navigates without full reload
            } else {
                return response.json().then(data => {
                    alert(data.error);
                });
            }
        })
        .catch(error => console.error('Error:', error));
    }

    render() {
        return (
            <form method="post" action="/accounts/login/" data-turbo="true" onSubmit={this.handleSubmit.bind(this)}>
                <input type="hidden" name="csrfmiddlewaretoken" value={document.querySelector('[name=csrfmiddlewaretoken]').value} />
                <div className="form-group">
                    <input type="text" id="username" name="username" placeholder="Username" required />
                    <i className="fas fa-user"></i>
                </div>
                <div className="form-group">
                    <input type="password" id="password" name="password" placeholder="Password" required />
                    <i className="fas fa-lock"></i>
                </div>
                <button type="submit">Login</button>
                <div className="forgot-password">
                    <a href="#">Forgot your password?</a>
                </div>
            </form>
        );
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const rootElement = document.getElementById('login-root');
    if (rootElement) {
        ReactDOM.render(<LoginForm />, rootElement);
    }
});
