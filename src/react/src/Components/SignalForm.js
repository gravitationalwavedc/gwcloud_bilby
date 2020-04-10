import React from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, smallerThan, notEmpty} from "../Utils/errors";



class SignalForm extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            data: {
                signalChoice: 'binaryBlackHole',
                signalModel: '',
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

    handleChange = (e, data) => {
        this.setState({
            ...this.state,
            data: {
                ...this.state.data,
                [data.name]: data.type === "checkbox" ? data.checked : data.value,
            },
        })
    }

    checkErrors = (name, value) => {
        let errors = []
        switch (name) {
            case 'mass1':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
            case 'mass2':
                errors = checkForErrors(smallerThan(this.state.data.mass1, 'Mass 1'), isNumber, notEmpty)(value)
                break;
            case 'luminosityDistance':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
            case 'psi':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
            case 'iota':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
            case 'phase':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
            case 'mergerTime':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
            case 'ra':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
            case 'dec':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
        }
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
        } else {
            this.props.updateParentState(this.state.data)
            this.props.nextStep()
        }
    }

    render() {
        const {data, errors} = this.state
        const noneOption = [{key: 'none', text: 'None', value: 'none'}]
        const signalOptions = [{key: 'binaryBlackHole', text: 'Binary Black Hole', value: 'binaryBlackHole'}]
        return (
            <React.Fragment>
                <BaseForm onChange={this.handleChange} validate={this.state.validate}
                    forms={this.props.dataType == 'open' ? [
                            {rowName: 'Signal Inject', form: <Form.Select name='signalChoice' placeholder="Select Signal Type" value={data.signalChoice} options={noneOption}/>},
                            {rowName: 'Signal Model', form: <Form.Select name='signalModel' placeholder="Select Signal Model" value={data.signalModel} options={signalOptions}/>},
                        ]
                        : [
                            {rowName: 'Signal Inject', form: <Form.Select name='signalChoice' placeholder="Select Signal Type" value={data.signalChoice} options={signalOptions}/>},
                            {rowName: 'Mass 1 (M\u2299)', form: <Form.Input name='mass1' placeholder="2.0" value={data.mass1}/>, errors: errors.mass1},
                            {rowName: 'Mass 2 (M\u2299)', form: <Form.Input name='mass2' placeholder="1.0" value={data.mass2}/>, errors: errors.mass2},
                            {rowName: 'Luminosity Distance (Mpc)', form: <Form.Input name='luminosityDistance' placeholder="1.0" value={data.luminosityDistance}/>, errors: errors.luminosityDistance},
                            {rowName: 'psi', form: <Form.Input name='psi' placeholder="1.0" value={data.psi}/>, errors: errors.psi},
                            {rowName: 'iota', form: <Form.Input name='iota' placeholder="1.0" value={data.iota}/>, errors: errors.iota},
                            {rowName: 'Phase', form: <Form.Input name='phase' placeholder="1.0" value={data.phase}/>, errors: errors.phase},
                            {rowName: 'Merger Time (GPS Time)', form: <Form.Input name='mergerTime' placeholder="1.0" value={data.mergerTime}/>, errors: errors.mergerTime},
                            {rowName: 'Right Ascension (radians)', form: <Form.Input name='ra' placeholder="1.0" value={data.ra}/>, errors: errors.ra},
                            {rowName: 'Declination (degrees)', form: <Form.Input name='dec' placeholder="1.0" value={data.dec}/>, errors: errors.dec},
                            {rowName: 'Same Signal for Model', form: <Form.Checkbox name='sameSignal' checked={data.sameSignal}/>},
                        ]
                    }
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

export default SignalForm;