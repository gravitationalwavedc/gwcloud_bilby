import React from "react";
import {Grid, Card, Segment, Item} from "semantic-ui-react";
import {createFragmentContainer, graphql} from "react-relay";
import JobResultFile from "./JobResultFile";
import * as Enumerable from "linq";

class JobParameters extends React.Component {
    constructor(props) {
        super(props);
        console.log(this.props)
    }


    render() {
        // const {start, jobStatus} = this.props.bilbyJobParameters
        return (
            <React.Fragment>
                <Grid centered textAlign='center' verticalAlign='middle'>
                    <Grid.Column>
                        <Item.Group>
                            <Item header='Data' description='Hello'/>
                            <Item header='Signal' description='Here'/>
                            <Item header='Priors' description='Are'/>
                            <Item header='Sampler' description='Parameters'/>
                        </Item.Group>
                    </Grid.Column>
                </Grid>
            </React.Fragment>
        )
    }
}

export default createFragmentContainer(JobParameters, {
    bilbyJobParameters: graphql`
        fragment JobParameters_bilbyJobParameters on BilbyJobNode {
            data {
                dataChoice
                hanford
                livingston
                virgo
                signalDuration
                samplingFrequency
                triggerTime
                hanfordMinimumFrequency
                hanfordMaximumFrequency
                hanfordChannel
                livingstonMinimumFrequency
                livingstonMaximumFrequency
                livingstonChannel
                virgoMinimumFrequency
                virgoMaximumFrequency
                virgoChannel
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
            prior {
                priorChoice
            }
            sampler {
                samplerChoice
            }
        }
    `
});