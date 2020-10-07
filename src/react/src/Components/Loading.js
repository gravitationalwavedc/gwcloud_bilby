import React from "react";
import Spinner from "react-bootstrap/Spinner";

const spinnerStyle = {
    top: "30%",
    left: "50%",
    position: "absolute",
    width: "5rem",
    height: "5rem",
    color: "#b6b7b9"
};

const Loading = () => 
  <Spinner animation="border" role="status" style={spinnerStyle}>
    <span className="sr-only">Loading...</span>
  </Spinner>
;

export default Loading;
