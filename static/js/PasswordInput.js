import { TextField } from '@material/web';
import React, { useState } from 'react';

const PasswordInput = ({ label }) => {
  const [showPassword, setShowPassword] = useState(false);
  const handleClickShowPassword = () => setShowPassword(!showPassword);

  return (
    <div>
      <TextField
        type={showPassword ? 'text' : 'password'}
        label={label}
        trailingIcon={
          <button onClick={handleClickShowPassword}>
            <i className={showPassword ? 'visibility' : 'visibility_off'}></i>
          </button>
        }
      />
    </div>
  );
};

export default PasswordInput;
