import React from "react";
import {Grid, Header, Image, Message, Step, Button, Label} from "semantic-ui-react";
import Link from 'found/lib/Link';
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../index";
import {graphql} from "graphql";

import {StartForm, DataForm, SignalForm, PriorsForm, SamplerForm, SubmitForm} from "./Forms";
import StepControl from "./Steps";

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

    handleChange = (e, data) => {
        this.setState({
            [data.name]: data.type === "checkbox" ? data.checked : data.value
        })
        console.log(this.state)
    }

    handleStepClick = (e, {stepnum}) => {
        this.setState({
            step: stepnum
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
            <Grid.Row>
                <Grid.Column>
                    <StepControl activeStep={step} onClick={this.handleStepClick}/>
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={3}>
                <Grid.Column>
                    {this.renderSwitch(step)}
                </Grid.Column>
            </Grid.Row>
            <Grid.Row columns={2}>
                <Grid.Column floated='left'>
                    {this.state.step!=1 ? <Button onClick={this.prevStep}>Back</Button> : null}
                </Grid.Column>
                <Grid.Column floated='right'>
                    <Button onClick={this.nextStep}>Continue</Button>
                </Grid.Column>
            </Grid.Row>
        </React.Fragment>
    }
}

export default StepForm;