import React from 'react';
import { Card, Col, Row } from 'react-bootstrap';

const FormCard = ({title, children}) => 
    <Card className="gw-form-card">
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
