import React from "react";
import {Button} from "semantic-ui-react";

class StartForm extends React.Component {
    saveAndContinue = (e) => {
        e.preventDefault();
        this.props.nextStep();
    }

    render() {
        // const {values} = this.props

        return(
            <div>
                <h1 className="ui centered">Start New Bilby Job</h1>
                <Button onClick={this.saveAndContinue}>Continue</Button>
            </div>
        )
    }
}

export default StartForm;