import React from "react";
import { Col } from "react-bootstrap";

const EventIDCell = ({ eventID }) => (
  <Col md={2}>
    {eventID ? (
      Object.values(eventID)
        .filter((value) => value)
        .map((value) => (
          <span key={value}>
            {value}
            <br />
          </span>
        ))
    ) : (
      <span>No event ids</span>
    )}
  </Col>
);

export default EventIDCell;
