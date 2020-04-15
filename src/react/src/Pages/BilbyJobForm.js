import React from "react";
import {Grid} from "semantic-ui-react";
import StepForm from "../Components/Forms/StepForm";
import { graphql, createFragmentContainer } from "react-relay";
import BilbyBasePage from "./BilbyBasePage";


class BilbyJobForm extends React.Component {
    constructor(props) {
        super(props);
        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: [
                {name: 'Job Form', path: '/bilby/job-form/'}
            ]
        }
    }
    
    render() {
        return (
            <BilbyBasePage title='Bilby Job Form' {...this.routing}>
                <Grid centered textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                    <StepForm data={this.props.data} {...this.routing}/>
                </Grid>
            </BilbyBasePage>
        )
    }
}


export default createFragmentContainer(BilbyJobForm, {
    data: graphql`
        fragment BilbyJobForm_data on Query @argumentDefinitions(
            jobId: {type: "ID!"}
        ){
            bilbyJob (id: $jobId){
                start {
                    name
                    description
                }
                data {
                    dataChoice
                    hanford
                    livingston
                    virgo
                    signalDuration
                    samplingFrequency
                    startTime
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
                priors {
                    mass1 {
                        type
                        value
                        min
                        max
                    }
                    mass2 {
                        type
                        value
                        min
                        max
                    }
                    luminosityDistance {
                        type
                        value
                        min
                        max
                    }
                    psi {
                        type
                        value
                        min
                        max
                    }
                    iota {
                        type
                        value
                        min
                        max
                    }
                    phase {
                        type
                        value
                        min
                        max
                    }
                    mergerTime {
                        type
                        value
                        min
                        max
                    }
                    ra {
                        type
                        value
                        min
                        max
                    }
                    dec {
                        type
                        value
                        min
                        max
                    }
                }
                sampler {
                    samplerChoice
                    number
                }
            }
            bilbyJobs {
                edges {
                    node {
                        name
                    }
                }
            }
        }
    `
});