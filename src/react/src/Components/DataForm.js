import React from "react";
import {Button} from "semantic-ui-react";

class DataForm extends React.Component {
    saveAndContinue = (e) => {
        this.props.nextStep()
    }

    back = (e) => {
        this.props.prevStep()
    }

    render() {
        // const {values} = this.props

        return(
            <div>
                <h1 className="ui centered">Data</h1>
                <Button onClick={this.back}>Back</Button>
                <Button onClick={this.saveAndContinue}>Continue</Button>
            </div>
        )
    }
}

export default DataForm;