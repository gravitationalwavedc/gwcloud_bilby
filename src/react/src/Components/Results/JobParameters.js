import React from "react";
import {Grid, Item, List, Table, Segment, Header} from "semantic-ui-react";
import {createFragmentContainer, graphql} from "react-relay";
import BasicTable from "../Utils/BasicTable";
import { unCamelCase } from "../../Utils/utilMethods";

class JobParameters extends React.Component {
    constructor(props) {
        super(props);
    }


    render() {
        const {data, signal, prior, sampler} = this.props.bilbyJobParameters
        const {
            dataChoice,
            hanford,
            livingston,
            virgo,
            signalDuration,
            samplingFrequency,
            triggerTime,
            hanfordMinimumFrequency,
            hanfordMaximumFrequency,
            hanfordChannel,
            livingstonMinimumFrequency,
            livingstonMaximumFrequency,
            livingstonChannel,
            virgoMinimumFrequency,
            virgoMaximumFrequency,
            virgoChannel
        } = data

        const {
            signalChoice,
            signalModel,
            mass1,
            mass2,
            luminosityDistance,
            psi,
            iota,
            phase,
            mergerTime,
            ra,
            dec
        } = signal


        const detectorRows = [
            hanford ? ['Hanford', hanfordMinimumFrequency, hanfordMaximumFrequency, hanfordChannel] : null,
            livingston ? ['Livingston', livingstonMinimumFrequency, livingstonMaximumFrequency, livingstonChannel] : null,
            virgo ? ['Virgo', virgoMinimumFrequency, virgoMaximumFrequency, virgoChannel] : null
        ]

        const miscDataRows = [
            ['Signal Duration', signalDuration],
            ['Sampling Frequency', samplingFrequency],
            ['Trigger Time', triggerTime]
        ]

        const injectedSignalRows = [
            ['Injected Signal', unCamelCase(signalChoice)],
            ['Mass 1', mass1],
            ['Mass 2', mass2],
            ['Luminosity Distance', luminosityDistance],
            ['psi', psi],
            ['iota', iota],
            ['Phase', phase],
            ['Merger Time', mergerTime],
            ['Right Ascension', ra],
            ['Declination', dec]
        ]

        return (
            <React.Fragment>
                <Grid centered textAlign='center' verticalAlign='middle' divided='vertically'>
                    <Grid.Row>
                        <Grid.Column width={4}>
                            <Header>
                                <Header.Subheader content='Data'/>
                                {unCamelCase(dataChoice)}
                            </Header>
                        </Grid.Column>
                        <Grid.Column width={12} >
                            <BasicTable headers={['', 'Minimum Frequency', 'Maximum Frequency', 'Channel']} rows={detectorRows}/>
                            <BasicTable headers={[]} rows={miscDataRows}/>
                        </Grid.Column>
                    </Grid.Row>
                    <Grid.Row>
                        <Grid.Column width={4}>
                            <Header>
                                <Header.Subheader content='Signal'/>
                                {unCamelCase(signalModel)}
                            </Header>
                        </Grid.Column>
                        <Grid.Column width={12} >
                            <BasicTable headers={[]} rows={injectedSignalRows}/>
                        </Grid.Column>
                    </Grid.Row>
                    <Grid.Row>
                        <Grid.Column width={4}>
                            <Header>
                                <Header.Subheader content='Prior'/>
                                {unCamelCase(prior.priorChoice)}
                            </Header>
                        </Grid.Column>
                    </Grid.Row>
                    <Grid.Row>
                        <Grid.Column width={4}>
                            <Header>
                                <Header.Subheader content='Sampler'/>
                                {unCamelCase(sampler.samplerChoice)}
                            </Header>
                        </Grid.Column>
                    </Grid.Row>
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