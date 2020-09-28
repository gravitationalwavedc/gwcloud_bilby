import React, { useState, useEffect } from "react";
import { Message, Icon, Container } from "semantic-ui-react";
import Floating from "./Floating";
import { usePrevious } from "../Utils/hooks";

function TemporaryMessage(props) {
    const [isVisible, setVisible] = useState(false)
    const prevVisible = usePrevious(isVisible)

    useEffect(() => {
        if (prevVisible === false) {
            setVisible(true)
        }
        
        const timeout = setTimeout(() => setVisible(false), props.timeout)
        return () => clearTimeout(timeout)
    })

    return isVisible && (
        <Floating>
            <Container>
                <Message success={props.success} error={!props.success} onDismiss={() => {setVisible(false)}}>
                    <Message.Content >
                        <Icon name={props.icon} />
                        {props.content}
                    </Message.Content>
                </Message>
            </Container>
        </Floating>
    )
}

export default TemporaryMessage