import React from "react";
import {Grid, Header, Image, Message, Step, Button, Label} from "semantic-ui-react";
import Link from 'found/lib/Link';
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../index";
import {graphql} from "graphql";

import {SamplerForm, SubmitForm} from "./Forms";
import StartForm from "./StartForm";
import DataForm from "./DataForm";
import SignalForm from "./SignalForm";
import PriorsForm from "./PriorsForm";
import StepControl from "./Steps";

class StepForm extends React.Component {
    constructor() {
        super();

        this.state = {
            step: 1,
            stepsCompleted: 1,
            start: null,
            data: null,
            signal: null,
            priors: null,
            sampler: {
                sampler: 'dynesty',
                number: ''
            }
        }
    }

    nextStep = () => {
        const {step, stepsCompleted} = this.state
        this.setState({
            step: step + 1,
            stepsCompleted: step == stepsCompleted ? step + 1 : stepsCompleted
        })
    }

    prevStep = () => {
        const {step} = this.state
        this.setState({
            step: step - 1
        })
    }

    handleChange = (form) => (e, data) => {
        this.setState({
            [form]: {
                ...this.state[form],
                [data.name]: data.type === "checkbox" ? data.checked : data.value,
            }
        })
        console.log(this.state[form])
    }

    handleChangeNew = (form) => (childState) => {
        this.setState({
            ...this.state,
            [form]: childState
        })
        console.log(this.state)
    }

    handleChangePriors = (form) => (param) => (e, data) => {
        this.setState({
            [form]: {
                ...this.state[form],
                [param]: {...this.state[form][param], [data.name]: data.type === "checkbox" ? data.checked : data.value}
            }
        })
    }

    handleStepClick = (e, {stepnum}) => {
        this.setState({
            step: stepnum
        })
    }

    handleSubmit = () => {
        if (this.state.signal.sameSignal) {
            this.setState({
                signal: {
                    ...this.state.signal,
                    signalModel: this.state.signal.signalType,
                    sameSignal: undefined
                }
            })
        }
        let signal = {...this.state.signal}
        delete signal.sameSignal
        commitMutation(harnessApi.getEnvironment("bilby"), {
            mutation: graphql`mutation StepFormSubmitMutation($input: BilbyJobMutationInput!)
                {
                  newBilbyJob(input: $input) 
                  {
                    result
                  }
                }`,
            variables: {
                input: {
                    start: this.state.start,
                    data: this.state.data,
                    signal: signal,
                    prior: this.state.priors,
                    sampler: this.state.sampler
                }
            },
            onCompleted: (response, errors) => {
                console.log(response)
            },
        })
    }


    renderSwitch(step) {
        switch(step) {
            case 1:
                return <StartForm state={this.state.start} updateParentState={this.handleChangeNew('start')} nextStep={this.nextStep}/>
            
            case 2:
                return <DataForm state={this.state.data} updateParentState={this.handleChangeNew('data')} prevStep={this.prevStep} nextStep={this.nextStep}/>

            case 3:
                return <SignalForm state={this.state.signal} updateParentState={this.handleChangeNew('signal')} prevStep={this.prevStep} nextStep={this.nextStep} dataType={this.state.data.dataType}/>

            case 4:
                return <PriorsForm state={this.state.priors} updateParentState={this.handleChangeNew('priors')} prevStep={this.prevStep} nextStep={this.nextStep}/>

            case 5:
                return <SamplerForm handleChange={this.handleChange('sampler')} formVals={this.state.sampler} />

            case 6:
                return <SubmitForm />
        }
    }

    render() {
        const {step, stepsCompleted} = this.state
        return <React.Fragment>
            <Grid.Row>
                <Grid.Column>
                    <StepControl activeStep={step} stepsCompleted={stepsCompleted} onClick={this.handleStepClick}/>
                </Grid.Column>
            </Grid.Row>
            {this.renderSwitch(step)}
        </React.Fragment>
    }
}

export default StepForm;