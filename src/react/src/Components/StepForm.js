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
            step: 1,
            start: {
                jobName: '',
                jobDescription: ''
            },
            data: {
                dataType: '',
                hanford: false,
                livingston: false,
                virgo: false,
                signalDuration: '',
                samplingFrequency: '',
                startTime: ''
            },
            signal: {
                signalType: '',
                mass1: '',
                mass2: '',
                luminosityDistance: '',
                psi: '',
                iota: '',
                phase: '',
                mergerTime: '',
                ra: '',
                dec: '',
                sameSignal: false
            },
            priors: {
                mass1: {type: 'fixed', value: '', min: '', max: ''},
                mass2: {type: 'fixed', value: '', min: '', max: ''},
                luminosityDistance: {type: 'fixed', value: '', min: '', max: ''},
                iota: {type: 'fixed', value: '', min: '', max: ''},
                psi: {type: 'fixed', value: '', min: '', max: ''},
                phase: {type: 'fixed', value: '', min: '', max: ''},
                mergerTime: {type: 'fixed', value: '', min: '', max: ''},
                ra: {type: 'fixed', value: '', min: '', max: ''},
                dec: {type: 'fixed', value: '', min: '', max: ''}
            },
            sampler: {
                sampler: 'dynesty',
                number: ''
            }
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

    handleChange = (form) => (e, data) => {
        this.setState({
            [form]: {...this.state[form], [data.name]: data.type === "checkbox" ? data.checked : data.value}
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
                return <StartForm handleChange={this.handleChange('start')} formVals={this.state.start}/>
            
            case 2:
                return <DataForm handleChange={this.handleChange('data')} formVals={this.state.data}/>

            case 3:
                return <SignalForm handleChange={this.handleChange('signal')} formVals={this.state.signal}/>

            case 4:
                return <PriorsForm handleChange={this.handleChangePriors('priors')} formVals={this.state.priors} />

            case 5:
                return <SamplerForm handleChange={this.handleChange('sampler')} formVals={this.state.sampler} />

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