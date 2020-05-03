import React from "react";
import {Grid} from "semantic-ui-react";
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../../index";
import { graphql, createFragmentContainer } from "react-relay";

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

        const initialState = {
            start: null,
            data: null,
            signal: null,
            priors: null,
            sampler: null
        }

        this.state = {
            step: 1,
            stepsCompleted: 1,
            ...initialState
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
                    signalModel: this.state.signal.signalChoice,
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
        const {bilbyJob} = this.props.data
        switch(step) {
            case 1:
                return <StartForm data={bilbyJob === null ? null : bilbyJob.start} state={this.state.start} updateParentState={this.handleChange('start')} nextStep={this.nextStep} jobNames={this.props}/>
            
            case 2:
                return <DataForm data={bilbyJob === null ? null : bilbyJob.data} state={this.state.data} updateParentState={this.handleChange('data')} prevStep={this.prevStep} nextStep={this.nextStep}/>

            case 3:
                return <SignalForm data={bilbyJob === null ? null : bilbyJob.signal} state={this.state.signal} updateParentState={this.handleChange('signal')} prevStep={this.prevStep} nextStep={this.nextStep} dataChoice={this.state.data.dataChoice}/>

            case 4:
                return <PriorsForm data={bilbyJob === null ? null : bilbyJob.priors} state={this.state.priors} updateParentState={this.handleChange('priors')} prevStep={this.prevStep} nextStep={this.nextStep}/>

            case 5:
                return <SamplerForm data={bilbyJob === null ? null : bilbyJob.sampler} state={this.state.sampler} updateParentState={this.handleChange('sampler')} prevStep={this.prevStep} nextStep={this.nextStep}/>

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

// export default StepForm;
export default createFragmentContainer(StepForm, {
    data: graphql`
        fragment StepForm_data on Query @argumentDefinitions(
            jobId: {type: "ID!"}
        ){
            bilbyJob (id: $jobId){
                start {
                    ...StartForm_data
                }
                data {
                    ...DataForm_data
                }
                signal {
                    ...SignalForm_data
                }
                priors {
                    ...PriorsForm_data
                }
                sampler {
                    ...SamplerForm_data
                }
            }
        }
    `
});