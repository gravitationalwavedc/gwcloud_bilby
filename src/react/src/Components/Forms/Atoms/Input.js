import React from 'react';
import { Form } from 'react-bootstrap';

const Input = ({formik, title, name, type, ...rest}) => 
    <Form.Group controlId={ name }>
        <Form.Label>{ title }</Form.Label>
        <Form.Control 
            name={ name }
            type={ type } 
            isValid={formik.touched[name] && !formik.errors[name]}
            isInvalid={!!formik.errors[name]}
            {...formik.getFieldProps(name)} {...rest}/>
        <Form.Control.Feedback type='invalid'>
            {formik.errors[name]}
        </Form.Control.Feedback>
    </Form.Group>;


export default Input;
