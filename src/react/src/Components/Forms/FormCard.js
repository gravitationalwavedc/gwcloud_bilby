import React from 'react';
import { Card, Col, Row } from 'react-bootstrap';

const FormCard = ({title, children, disabled, ...rest}) => 
    <Card className={disabled ? 'gw-form-card disabled' : 'gw-form-card'} {...rest}>
        <Card.Body>
            <Row>
                <Col md={4}>
                    <h3>{title}</h3>
                </Col>
                <Col>
                    {children}
                </Col>
            </Row>
        </Card.Body>
    </Card>;

export default FormCard;
