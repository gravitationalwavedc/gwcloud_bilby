import React from "react";
import {Grid, Header, Image, Message, Step, Button} from "semantic-ui-react";
import Link from 'found/lib/Link';
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../index";
import {graphql} from "graphql";

import {StartForm, DataForm, SignalForm, PriorsForm, SamplerForm, SubmitForm} from "./Forms";

class StepForm extends React.Component {
    constructor() {
        super();

        this.state = {
            step: 1
        }
    }

    // handleChange = () => {
    //     this.setState({})
    // }

    nextStep = () => {
        const {step} = this.state
        this.setState({
            step: step + 1
        })
    }

    prevStep = () => {
        const {step} = this.state
        this.setState({
            step: step - 1
        })
    }

    handleChange = (e) => {
        this.setState({
            [e.target.name]: e.target.value
        })
    }

    renderSwitch(step) {
        switch(step) {
            case 1:
                return <StartForm handleChange={this.handleChange}/>
            
            case 2:
                return <DataForm handleChange={this.handleChange}/>

            case 3:
                return <SignalForm handleChange={this.handleChange} />

            case 4:
                return <PriorsForm handleChange={this.handleChange} />

            case 5:
                return <SamplerForm handleChange={this.handleChange} />

            case 6:
                return <SubmitForm handleChange={this.handleChange} />
        }
    }

    render() {
        const {step} = this.state
        return <React.Fragment>
            {this.renderSwitch(step)}
            {this.state.step!=1 ? <Button onClick={this.prevStep}>Back</Button> : null}
            <Button onClick={this.nextStep}>Continue</Button>
        </React.Fragment>
    }
}

export default StepForm;