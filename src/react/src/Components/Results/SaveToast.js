import React from 'react';
import { Toast } from 'react-bootstrap';

const SaveToast = ({ saved, show, message, onClose }) => {
    return show && 
        <Toast 
            style={{position: 'absolute', top: '56px', right:'50px'}} 
            onClose={onClose} 
            show={show} 
            delay={3000} 
            autohide>
            <Toast.Header>{saved ? 'Saved' : 'Save Failed'}</Toast.Header>
            <Toast.Body>{message}</Toast.Body>
        </Toast>
}

export default SaveToast