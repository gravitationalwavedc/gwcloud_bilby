import React from 'react';
import Spinner from 'react-bootstrap/Spinner';

const spinnerStyle = {
    top: '30%',
    left: 0,
    right: 0,
    margin: '0 auto',
    position: 'absolute',
    width: '5rem',
    height: '5rem',
};

const Loading = () => 
    <Spinner animation="border" role="status" style={spinnerStyle}>
        <span className="sr-only">Loading...</span>
    </Spinner>
;

export default Loading;
