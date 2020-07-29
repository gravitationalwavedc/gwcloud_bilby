import React, { Component } from 'react';
// Required to use React portals
import ReactDOM from 'react-dom';

function Floating(props) {
    const style = {
        top: "10%",
        right: "5%",
        maxWidth: "10%",
        position: "fixed",
    }
    
    const float = (
      <div style={style}>
        {props.children}
      </div>
    );

    return ReactDOM.createPortal(float, document.body)
}

export default Floating;