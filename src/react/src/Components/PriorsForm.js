import React from "react";
import {BaseForm, PriorsFormInput} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, handlePriors} from "../Utils/errors";



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

    checkErrors = (name, value) => {
        const errors = checkForErrors(handlePriors)(value)
        return errors;
    }

    handleErrors = () => {
        let {data, errors} = this.state
        for (const [name, val] of Object.entries(data)) {
            errors[name] = this.checkErrors(name, val)
        }
        this.setState({
            ...this.state,
            errors: errors
        })
    }

    prevStep = () => {
        this.props.prevStep()
    }

    nextStep = () => {
        this.handleErrors()
        const notEmpty = (arr) => {return Boolean(arr && arr.length)}
        if (Object.values(this.state.errors).some(notEmpty)) {
            this.setState({
              ...this.state,
              validate: true  
            })
            console.log('hello', this.state)
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
                        {form: <PriorsFormInput title={'Mass 1 (M\u2299)'} name='mass1' placeholder='2' value={data.mass1}/>, errors: errors.mass1},
                        {form: <PriorsFormInput title={'Mass 2 (M\u2299)'} name='mass2' placeholder='2' value={data.mass2}/>, errors: errors.mass2},
                        {form: <PriorsFormInput title='Luminosity Distance (Mpc)' name='luminosityDistance' placeholder='2' value={data.luminosityDistance}/>, errors: errors.luminosityDistance},
                        {form: <PriorsFormInput title='iota' name='iota' placeholder='2' value={data.iota}/>, errors: errors.iota},
                        {form: <PriorsFormInput title='psi' name='psi' placeholder='2' value={data.psi}/>, errors: errors.psi},
                        {form: <PriorsFormInput title='phase' name='phase' placeholder='2' value={data.phase}/>, errors: errors.phase},
                        {form: <PriorsFormInput title='Merger Time (GPS Time)' name='mergerTime' placeholder='2' value={data.mergerTime}/>, errors: errors.mergerTime},
                        {form: <PriorsFormInput title='Right Ascension (Radians)' name='ra' placeholder='2' value={data.ra}/>, errors: errors.ra},
                        {form: <PriorsFormInput title='Declination (Degrees)' name='dec' placeholder='2' value={data.dec}/>, errors: errors.dec},
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