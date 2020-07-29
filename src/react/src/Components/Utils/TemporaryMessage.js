import React from "react";
import { Message, Icon, Container } from "semantic-ui-react";
import Floating from "./Floating";

class TemporaryMessage extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            isVisible: false
        }
    }

    onDismiss = () => {
        this.setState({ isVisible: false })
    }

    componentDidUpdate(prevProps, prevState) {
        clearTimeout(this.timeout)
        if (!prevState.isVisible) {
            this.setState({ isVisible: true })
        } else if (this.state.isVisible) {
            this.timeout = setTimeout(() => this.setState({ isVisible: false }), this.props.timeout)
        }
    }

    render() {
        return this.state.isVisible && (
            <Floating>
                <Container>
                    <Message success={this.props.success} error={!this.props.success} onDismiss={this.onDismiss}>
                        <Message.Content >
                            <Icon name={this.props.icon} />
                            {this.props.content}
                        </Message.Content>
                    </Message>
                </Container>
            </Floating>
        )
    }
}
export default TemporaryMessage