import React from "react";
import { Card, Col, Row } from "react-bootstrap";

const cardStyle = {
  borderTop: "8px solid #0592EB", 
  borderLeft: "none", 
  borderRight: "none", 
  borderBottom: "none", 
  borderRadius: 0, 
  boxShadow: "0 4px 8px rgba(0, 0, 0, 0.2)"
};

const FormCard = ({title, children}) => 
<Card style={cardStyle} className="mb-4">
  <Card.Body>
    <Row>
      <Col md={4}>
        <h2>{title}</h2>
      </Col>
      <Col>
        {children}
      </Col>
    </Row>
  </Card.Body>
</Card>;

export default FormCard;
