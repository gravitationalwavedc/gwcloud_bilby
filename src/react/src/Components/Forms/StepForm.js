import React from "react";
import {Grid} from "semantic-ui-react";
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../../index";
import {graphql} from "graphql";

import StartForm from "./StartForm";
import DataForm from "./DataForm";
import SignalForm from "./SignalForm";
import PriorsForm from "./PriorsForm";
import SamplerForm from "./SamplerForm";
import SubmitForm from "./SubmitForm";

import StepControl from "../Utils/Steps";

class StepForm extends React.Component {
    constructor(props) {
        super(props);
        const initialState = this.props.data.bilbyJob === null ? {
            start: null,
            data: null,
            signal: null,
            priors: null,
            sampler: null
        } : this.props.data.bilbyJob

        this.state = {
            step: 1,
            stepsCompleted: 1,
            ...initialState
        }

        this.jobNames = this.props.data.bilbyJobs.edges.map(({node}) => node.name)
    }

    nextStep = () => {
        const {step, stepsCompleted} = this.state
        this.setState({
            step: step + 1,
            stepsCompleted: step == stepsCompleted ? step + 1 : stepsCompleted
        })
        console.log(this.state)
    }

    prevStep = () => {
        const {step} = this.state
        this.setState({
            step: step - 1
        })
    }

    handleChange = (form) => (childState) => {
        this.setState({
            ...this.state,
            [form]: childState
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
                return <StartForm state={this.state.start} updateParentState={this.handleChange('start')} nextStep={this.nextStep} jobNames={this.jobNames}/>
            
            case 2:
                return <DataForm state={this.state.data} updateParentState={this.handleChange('data')} prevStep={this.prevStep} nextStep={this.nextStep}/>

            case 3:
                return <SignalForm state={this.state.signal} updateParentState={this.handleChange('signal')} prevStep={this.prevStep} nextStep={this.nextStep} dataType={this.state.data.dataType}/>

            case 4:
                return <PriorsForm state={this.state.priors} updateParentState={this.handleChange('priors')} prevStep={this.prevStep} nextStep={this.nextStep}/>

            case 5:
                return <SamplerForm state={this.state.sampler} updateParentState={this.handleChange('sampler')} prevStep={this.prevStep} nextStep={this.nextStep}/>

            case 6:
                return <SubmitForm prevStep={this.prevStep} onSubmit={this.handleSubmit}/>
        }
    }

    render() {
        const {step, stepsCompleted} = this.state
        return <React.Fragment>
            <Grid.Row>
                <Grid.Column textAlign='center'>
                    <StepControl activeStep={step} stepsCompleted={stepsCompleted} onClick={this.handleStepClick}/>
                </Grid.Column>
            </Grid.Row>
            {this.renderSwitch(step)}
        </React.Fragment>
    }
}

export default StepForm;