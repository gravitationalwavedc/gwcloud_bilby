import React from "react";
import BaseForm from "./BaseForm";
import {createValidationFunction, isANumber, isSmallerThan, isNotEmpty, isLongerThan, isValidJobName} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";
import { mergeUnlessNull } from "../../Utils/utilMethods";
import { SelectField, InputField, FormSegment } from "./Forms";
import { Grid } from "semantic-ui-react";


function SignalForm(props) {
    const formProps = {
        initialValues: mergeUnlessNull(
            {
                start: {
                    name: "",
                    description: "",
                    private: false
                },
                signalChoice: 'binaryBlackHole',
                signalModel: 'binaryBlackHole',
                mass1: '30',
                mass2: '25',
                luminosityDistance: '2000',
                psi: '0.4',
                iota: '2.659',
                phase: '1.3',
                mergerTime: '1126259642.413',
                ra: '1.375',
                dec: '-1.2108',
            },
            props.data === null ? null : {...props.data.signal, start: props.data.start},
            props.state
        ),
        onSubmit: (values) => {
            const {start, ...signal} = values
            props.updateParentState('start')(start)
            props.updateParentState('signal')(signal)
        },
        validate: (values) => createValidationFunction(
            {
                "start.name": [isLongerThan(5), isValidJobName],
                mass1: [isANumber, isNotEmpty],
                mass2: [isSmallerThan(values.mass1, 'Mass 1'), isANumber, isNotEmpty],
                luminosityDistance: [isANumber, isNotEmpty],
                psi: [isANumber, isNotEmpty],
                iota: [isANumber, isNotEmpty],
                phase: [isANumber, isNotEmpty],
                mergerTime: [isANumber, isNotEmpty],
                ra: [isANumber, isNotEmpty],
                dec: [isANumber, isNotEmpty],
            },
            values
        ),
        linkedValues: (fieldName, fieldValue, state) => {
            switch (fieldName) {
                case 'sameSignal':
                    if (fieldValue) {
                        return {signalModel: state.values.signalChoice}
                    }
                    break;
                default:
                    break;
            }
    
        }
    }
    
    function setForms(values) {
        const signalOptions = [
            {key: 'binaryBlackHole', text: 'Binary Black Hole', value: 'binaryBlackHole'},
            {key: 'binaryNeutronStar', text: 'Binary Neutron Star', value: 'binaryNeutronStar'},
        ]
        
        const signalInjectOptions = props.openData ? [{key: 'none', text: 'None', value: 'none'}].concat(signalOptions) : signalOptions
        const formToggle = ['none', 'binaryBlackHole', 'binaryNeutronStar'].indexOf(values.signalChoice)

        const forms = {
            signalChoice: <SelectField label="Injection" name="signalChoice" placeholder="Select Signal Type" options={signalInjectOptions}/>,
            signalModel: <SelectField label="Model" name="signalModel" placeholder="Select Signal Type" options={signalOptions}/>,
            mass1: <InputField label={"Mass 1 (M\u2299)"} name="mass1" />,
            mass2: <InputField label={"Mass 2 (M\u2299)"} name="mass2" />,
            luminosityDistance: <InputField label="Luminosity Distance (Mpc)" name="luminosityDistance" />,
            psi: <InputField label="psi" name="psi" />,
            iota: <InputField label="iota" name="iota" />,
            phase: <InputField label="Phase" name="phase" />,
            mergerTime: <InputField label="Merger Time (GPS Time)" name="mergerTime" />,
            ra: <InputField label="Right Ascension (radians)" name="ra" />,
            dec: <InputField label="Declination (degrees)" name="dec" />,
        }

        return (
            <React.Fragment>
                <FormSegment header="Signal">
                    <Grid.Row columns={2}>
                        <Grid.Column>
                            {forms.signalChoice}
                        </Grid.Column>
                        <Grid.Column>
                            {props.openData && forms.signalModel}
                        </Grid.Column>
                    </Grid.Row>
                </FormSegment>
                {
                    formToggle > 0 && <FormSegment header="Injected Signal Parameters" subheader={values.signalChoice}>
                        <Grid.Row columns={2}>
                            <Grid.Column>
                                {forms.mass1}
                            </Grid.Column>
                            <Grid.Column>
                                {forms.mass2}
                            </Grid.Column>
                        </Grid.Row>
                        <Grid.Row columns={2}>
                            <Grid.Column>
                                {forms.luminosityDistance}
                            </Grid.Column>
                            <Grid.Column>
                                {forms.mergerTime}
                            </Grid.Column>
                        </Grid.Row>
                        <Grid.Row columns={2}>
                            <Grid.Column>
                                {forms.psi}
                                {forms.phase}
                            </Grid.Column>
                            <Grid.Column>
                                {forms.iota}
                            </Grid.Column>
                        </Grid.Row>
                        <Grid.Row columns={2}>
                            <Grid.Column>
                                {forms.ra}
                            </Grid.Column>
                            <Grid.Column>
                                {forms.dec}
                            </Grid.Column>
                        </Grid.Row>
                    </FormSegment>
                }
            </React.Fragment>
        )
    }

    return <BaseForm formProps={formProps} setForms={setForms}/>
}

export default createFragmentContainer(SignalForm, {
    data: graphql`
        fragment SignalForm_data on BilbyJobNode {
            start {
                name
                description
                private
            }
            signal {
                signalChoice
                signalModel
                mass1
                mass2
                luminosityDistance
                psi
                iota
                phase
                mergerTime
                ra
                dec
            }
        }
    `
});

