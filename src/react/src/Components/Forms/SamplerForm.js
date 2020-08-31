import React from "react";
import BaseForm from "./BaseForm";
import {createValidationFunction, isLongerThan, isValidJobName, isNotEmpty, isAnInteger, isAPositiveInteger, isLargerThan, isAPositiveNumber} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";
import { mergeUnlessNull } from "../../Utils/utilMethods";
import { SelectField, InputField, FormSegment } from "./Forms";
import { Grid } from "semantic-ui-react";


function SamplerForm(props) {
    const formProps = {
        initialValues: mergeUnlessNull(
            {
                start: {
                    name: "",
                    description: "",
                    private: false
                },
                sampler: {
                    samplerChoice: 'dynesty',
                    nlive: '1000',
                    nact: '10',
                    maxmcmc: '5000',
                    walks: '1000',
                    dlogz: '0.1',
                    cpus: '1'
                },
                prior: {
                    priorChoice: '4s'
                }
            },
            props.data === null ? null : props.data,
            props.state
        ),
        onSubmit: (values) => {
            const {start, prior, sampler} = values
            props.updateParentState('start')(start)
            props.updateParentState('prior')(prior)
            props.updateParentState('sampler')(sampler)
        },
        validate: (values) => createValidationFunction(
            {
                "start.name": [isLongerThan(5), isValidJobName],
                "sampler.nlive": [isLargerThan(100), isAnInteger, isNotEmpty],
                "sampler.nact": [isAPositiveInteger, isNotEmpty],
                "sampler.maxmcmc": [isAPositiveInteger, isNotEmpty],
                "sampler.walks": [isAPositiveInteger, isNotEmpty],
                "sampler.dlogz": [isAPositiveNumber, isNotEmpty],
                "sampler.cpus": [isAPositiveInteger, isNotEmpty],
            },
            values
        ),
    }

    function setForms(values) {
        const forms = {
            priorChoice: <SelectField label="Default Prior" name="prior.priorChoice" placeholder="Select Default Prior" options={
                [
                    {key: 'high_mass', text: 'High mass', value: 'high_mass'},
                    {key: '4s', text: '4s', value: '4s'},
                    {key: '8s', text: '8s', value: '8s'},
                    {key: '16s', text: '16s', value: '16s'},
                    {key: '32s', text: '32s', value: '32s'},
                    {key: '64s', text: '64s', value: '64s'},
                    {key: '128s', text: '128s', value: '128s'},
                    {key: '128s_tidal', text: '128s tidal', value: '128s_tidal'},
                ]
            }/>,
            samplerChoice: <SelectField label="Sampler" name="sampler.samplerChoice" placeholder="Select Sampler" options={[
                {key: 'dynesty', text: 'Dynesty', value: 'dynesty'},
            ]}/>,
            nlive: <InputField label="Number of live points" name="sampler.nlive" />,
            nact: <InputField label="Number of auto-correlation steps" name="sampler.nact" />,
            maxmcmc: <InputField label="Maximum number of steps" name="sampler.maxmcmc" />,
            walks: <InputField label="Minimum number of walks" name="sampler.walks" />,
            dlogz: <InputField label="Stopping criteria" name="sampler.dlogz" />,
            cpus: <InputField label="Number of CPUs for parallelisation" name="sampler.cpus" disabled />
        }

        return (
            <React.Fragment>
                <FormSegment header="Prior">
                    <Grid.Row columns={2}>
                        <Grid.Column>
                            {forms.priorChoice}
                        </Grid.Column>
                    </Grid.Row>
                </FormSegment>
                <FormSegment header="Sampler">
                    <Grid.Row columns={2}>
                        <Grid.Column>
                            {forms.samplerChoice}
                        </Grid.Column>
                    </Grid.Row>
                </FormSegment>
                <FormSegment header="Sampler Parameters" subheader={values.samplerChoice}>
                    <Grid.Row columns={2}>
                        <Grid.Column>
                            {forms.nlive}
                        </Grid.Column>
                        <Grid.Column>
                            {forms.nact}
                        </Grid.Column>
                    </Grid.Row>
                    <Grid.Row columns={2}>
                        <Grid.Column>
                            {forms.maxmcmc}
                            {forms.dlogz}
                        </Grid.Column>
                        <Grid.Column>
                            {forms.walks}
                        </Grid.Column>
                    </Grid.Row>
                </FormSegment>
            </React.Fragment>
        )
    }

    return <BaseForm formProps={formProps} setForms={setForms}/>
}

export default createFragmentContainer(SamplerForm, {
    data: graphql`
        fragment SamplerForm_data on BilbyJobNode {
            start {
                name
                description
                private
            }
            sampler {
                samplerChoice
                nlive
                nact
                maxmcmc
                walks
                dlogz
                cpus
            }
            prior {
                priorChoice
            }
        }
    `
});