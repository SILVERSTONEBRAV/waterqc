import React from 'react';
import PasswordInput from './PasswordInput';

const LoginForm = () => {
  const handleSubmit = (event) => {
    event.preventDefault();
    // Handle form submission logic here
  };

  return (
    <form method="post" action="/login" onSubmit={handleSubmit}>
      <PasswordInput label="Password" />
      <button type="submit">Submit</button>
    </form>
  );
};

export default LoginForm;
