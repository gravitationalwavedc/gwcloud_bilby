import React from "react";
import {BaseForm, PriorsFormInput} from "./Forms";
import {Grid, Button, Form} from "semantic-ui-react";
import {checkForErrors, handlePriors} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";


class PriorsForm extends React.Component {
    constructor(props) {
        super(props);
        const initialData = {
            priorChoice: '4s'
            // mass1: {type: 'fixed', value: '', min: '', max: ''},
            // mass2: {type: 'fixed', value: '', min: '', max: ''},
            // luminosityDistance: {type: 'fixed', value: '', min: '', max: ''},
            // iota: {type: 'fixed', value: '', min: '', max: ''},
            // psi: {type: 'fixed', value: '', min: '', max: ''},
            // phase: {type: 'fixed', value: '', min: '', max: ''},
            // mergerTime: {type: 'fixed', value: '', min: '', max: ''},
            // ra: {type: 'fixed', value: '', min: '', max: ''},
            // dec: {type: 'fixed', value: '', min: '', max: ''}
        }


        const errors = {}
        Object.keys(initialData).map((key) => {
            errors[key] = []
        })

        var data = (this.props.data !== null) ? this.props.data : initialData
        data = (this.props.state !== null) ? this.props.state : data
        this.state = {
            data: data,
            errors: errors,
            validate: false
        }
        this.forms = [
            {
                label: 'Default Prior', name: 'priorChoice', form: <Form.Select placeholder="Select Default Prior" options={
                    [
                        {key: '4s', text: '4s', value: '4s'},
                        {key: '8s', text: '8s', value: '8s'},
                        {key: '16s', text: '16s', value: '16s'},
                        {key: '32s', text: '32s', value: '32s'},
                        {key: '64s', text: '64s', value: '64s'},
                        {key: '128s', text: '128s', value: '128s'},
                    ]
                }/>
            },
            // {name: 'mass1', form: <PriorsFormInput title={'Mass 1 (M\u2299)'}/>, errFunc: checkForErrors(handlePriors)},
            // {name: 'mass2', form: <PriorsFormInput title={'Mass 2 (M\u2299)'}/>, errFunc: checkForErrors(handlePriors)},
            // {name: 'luminosityDistance', form: <PriorsFormInput title={'Luminosity Distance (Mpc)'}/>, errFunc: checkForErrors(handlePriors)},
            // {name: 'iota', form: <PriorsFormInput title={'iota'}/>, errFunc: checkForErrors(handlePriors)},
            // {name: 'psi', form: <PriorsFormInput title={'psi'}/>, errFunc: checkForErrors(handlePriors)},
            // {name: 'phase', form: <PriorsFormInput title={'phase'}/>, errFunc: checkForErrors(handlePriors)},
            // {name: 'mergerTime', form: <PriorsFormInput title={'Merger Time (GPS Time)'}/>, errFunc: checkForErrors(handlePriors)},
            // {name: 'ra', form: <PriorsFormInput title={'Right Ascension (Radians)'}/>, errFunc: checkForErrors(handlePriors)},
            // {name: 'dec', form: <PriorsFormInput title={'Declination (Degrees)'}/>, errFunc: checkForErrors(handlePriors)}
        ]
    }

    handleChange = ({name, value, errors}) => {
        this.setState(prevState => ({
            data: {
                ...prevState.data,
                [name]: value,
            },
            errors: {
                ...prevState.errors,
                [name]: errors
            }
        }))
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
                <BaseForm data={data} errors={errors} forms={this.forms} onChange={this.handleChange} validate={this.state.validate}/>
                <Grid.Row columns={2}>
                    <Grid.Column floated='left'>
                        <Button onClick={this.prevStep}>Back</Button>
                    </Grid.Column>
                    <Grid.Column floated='right'>
                        <Button onClick={this.nextStep}>Save and Continue</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

// export default PriorsForm;
export default createFragmentContainer(PriorsForm, {
    data: graphql`
        fragment PriorsForm_data on PriorType {
            priorChoice
        }
    `
});
// export default createFragmentContainer(PriorsForm, {
//     data: graphql`
//         fragment PriorsForm_data on OutputPriorType {
//             mass1 {
//                 type
//                 value
//                 min
//                 max
//             }
//             mass2 {
//                 type
//                 value
//                 min
//                 max
//             }
//             luminosityDistance {
//                 type
//                 value
//                 min
//                 max
//             }
//             psi {
//                 type
//                 value
//                 min
//                 max
//             }
//             iota {
//                 type
//                 value
//                 min
//                 max
//             }
//             phase {
//                 type
//                 value
//                 min
//                 max
//             }
//             mergerTime {
//                 type
//                 value
//                 min
//                 max
//             }
//             ra {
//                 type
//                 value
//                 min
//                 max
//             }
//             dec {
//                 type
//                 value
//                 min
//                 max
//             }
//         }
//     `
// });