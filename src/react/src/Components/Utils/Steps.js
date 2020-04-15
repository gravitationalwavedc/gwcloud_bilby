import React from "react";
import {Step, Label} from "semantic-ui-react";

class StepControl extends React.Component {
    constructor(props) {
        super(props);
        this.stepList = [
            {key: 1, stepnum: 1, link: true, onClick: this.props.onClick, title: 'Start', description: 'Start a new job', icon: <Label circular content='1' size='big'/>},
            {key: 2, stepnum: 2, link: true, onClick: this.props.onClick, title: 'Data', description: 'Select the data', icon: <Label circular content='2' size='big'/>},
            {key: 3, stepnum: 3, link: true, onClick: this.props.onClick, title: 'Signal', description: 'Inject a signal', icon: <Label circular content='3' size='big'/>},
            {key: 4, stepnum: 4, link: true, onClick: this.props.onClick, title: 'Priors', description: 'State priors', icon: <Label circular content='4' size='big'/>},
            {key: 5, stepnum: 5, link: true, onClick: this.props.onClick, title: 'Sampler', description: 'Choose sampler', icon: <Label circular content='5' size='big'/>},
            {key: 6, stepnum: 6, link: true, onClick: this.props.onClick, title: 'Submit', description: 'Submit your job', icon: <Label circular content='6' size='big'/>}
        ]
    }

    handleSwitch() {
        for (const element of this.stepList) {
            element.active = element.key == this.props.activeStep ? true : false
            element.disabled = element.key > this.props.stepsCompleted ? true : false
        }
    }

    render() {
        this.handleSwitch()
        return(
            <Step.Group items={this.stepList}/>
        )
    }
}

export default StepControl;