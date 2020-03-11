import React from "react";
import {BaseForm, PriorsFormInput} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, smallerThan} from "../Utils/errors";



class PriorsForm extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            data: {
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

            errors: {
                mass1: [],
                mass2: [],
                luminosityDistance: [],
                psi: [],
                iota: [],
                phase: [],
                mergerTime: [],
                ra: [],
                dec: [],
            },

            validate: false
        }
        this.state.data = this.props.state === null ? this.state.data : this.props.state
    }

    handleChange = (name, formData) => {
        this.setState({
            ...this.state,
            data: {
                ...this.state.data,
                [name]: formData
            },
        })
    }

    handleErrors = (data) => {
        let {errors} = this.state
        return errors;
    }

    prevStep = () => {
        this.props.prevStep()
    }

    nextStep = () => {
        const notEmpty = (arr) => {return Boolean(arr && arr.length)}
        if (Object.values(this.state.errors).some(notEmpty)) {
            this.setState({
              ...this.state,
              validate: true  
            })
        } else {
            this.props.updateParentState(this.state.data)
            this.props.nextStep()
        }
    }

    render() {
        const {data, errors} = this.state
        return (
            <React.Fragment>
                <BaseForm onChange={this.handleChange} validate={this.state.validate}
                    forms={[
                        {form: <PriorsFormInput title={'Mass 1 (M\u2299)'} name='mass1' placeholder='2' value={data.mass1}/>},
                        {form: <PriorsFormInput title={'Mass 2 (M\u2299)'} name='mass2' placeholder='2' value={data.mass2}/>},
                        {form: <PriorsFormInput title='Luminosity Distance (Mpc)' name='luminosityDistance' placeholder='2' value={data.luminosityDistance}/>},
                        {form: <PriorsFormInput title='iota' name='iota' placeholder='2' value={data.iota}/>},
                        {form: <PriorsFormInput title='psi' name='psi' placeholder='2' value={data.psi}/>},
                        {form: <PriorsFormInput title='phase' name='phase' placeholder='2' value={data.phase}/>},
                        {form: <PriorsFormInput title='Merger Time (GPS Time)' name='mergerTime' placeholder='2' value={data.mergerTime}/>},
                        {form: <PriorsFormInput title='Right Ascension (Radians)' name='ra' placeholder='2' value={data.ra}/>},
                        {form: <PriorsFormInput title='Declination (Degrees)' name='dec' placeholder='2' value={data.dec}/>},
                    ]}
                />
                <Grid.Row columns={2}>
                    <Grid.Column floated='left'>
                        <Button onClick={this.prevStep}>Back</Button>
                    </Grid.Column>
                    <Grid.Column floated='right'>
                        <Button onClick={this.nextStep}>Continue</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default PriorsForm;