import React from "react";
import {Grid} from "semantic-ui-react";
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../../index";
import {graphql, createFragmentContainer} from "react-relay";

import DataForm from "./DataForm";
import SignalForm from "./SignalForm";
import SamplerForm from "./SamplerForm";
import SubmitForm from "./SubmitForm";

import {StepController} from "../Utils/Steps";
import {useState} from "../../Utils/hooks";

const initialState = {
    start: null,
    data: null,
    signal: null,
    prior: null,
    sampler: null
}

function StepForm(props) {
    const [values, setValues] = useState(initialState)
    const [jobErrors, setJobErrors] = useState([])

    const handleChange = (form) => (childState) => {
        setValues(prevValues => ({
            ...prevValues,
            [form]: {
                ...prevValues[form],
                ...childState
            }
        }))
    }

    const handleSubmit = () => {
        const {start, data, signal, prior, sampler} = values
        commitMutation(harnessApi.getEnvironment("bilby"), {
            mutation: graphql`mutation StepFormSubmitMutation($input: BilbyJobMutationInput!)
                {
                  newBilbyJob(input: $input) 
                  {
                    result {
                      jobId
                    }
                  }
                }`,
            variables: {
                input: {
                    start: start,
                    data: data,
                    signal: signal,
                    prior: prior,
                    sampler: sampler
                }
            },
            onCompleted: (response, errors) => {
                if (errors) {
                    setJobErrors(errors)
                } else {
                    // Job was created successfully
                    props.router.replace('/bilby/job-results/' + response.newBilbyJob.result.jobId + "/")
                }
            },
        })
    }

    const renderSwitch = (step) => {
        const {bilbyJob} = props.data
        const {start, data, signal, prior, sampler} = values
        switch (step) {
            case 1:
                return <DataForm data={bilbyJob} state={{start, ...data}} updateParentState={handleChange}/>

            case 2:
                return <SignalForm data={bilbyJob} state={{start, ...signal}} updateParentState={handleChange}
                                   openData={data.dataChoice === 'open'}/>

            case 3:
                return <SamplerForm data={bilbyJob} state={{start, sampler, prior}} updateParentState={handleChange}/>

            case 4:
                return <SubmitForm onSubmit={handleSubmit} state={values} errors={jobErrors}/>

            default:
                return <div>End: {step}</div>
        }
    }

    const steps = [
        {title: 'Data', description: 'Select the data'},
        {title: 'Signal', description: 'Inject a signal'},
        {title: 'Priors and Sampler', description: 'State priors and choose sampler'},
        {title: 'Review and Submit', description: 'Review job parameters and submit'}
    ]

    return (
        <Grid.Column width={14}>
            <StepController steps={steps}>
                {renderSwitch}
            </StepController>
        </Grid.Column>

    )
}

export default createFragmentContainer(StepForm,
    {
        data: graphql`
        fragment StepForm_data on Query @argumentDefinitions(
            jobId: {type: "ID!"}
        ){
            bilbyJob (id: $jobId){
                ...DataForm_data
                ...SignalForm_data
                ...SamplerForm_data
            }
        }
        `
    }
);