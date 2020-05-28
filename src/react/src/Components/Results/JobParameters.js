import React from "react";
import {Grid, Item, List} from "semantic-ui-react";
import {createFragmentContainer, graphql} from "react-relay";
import BasicTable from "../Utils/BasicTable";

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

        const detectorRows = [
            hanford ? ['Hanford', hanfordMinimumFrequency, hanfordMaximumFrequency, hanfordChannel] : null,
            livingston ? ['Livingston', livingstonMinimumFrequency, livingstonMaximumFrequency, livingstonChannel] : null,
            virgo ? ['Virgo', virgoMinimumFrequency, virgoMaximumFrequency, virgoChannel] : null
        ]

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

        return (
            <React.Fragment>
                <Grid centered textAlign='center' verticalAlign='middle'>
                    <Grid.Column>
                        <Item.Group>
                            <Item>
                                <Item.Content>
                                    <Item.Header content={dataChoice.charAt(0).toUpperCase() + dataChoice.slice(1) + ' Data'}/>
                                    <Item.Description>
                                        <BasicTable headers={['Detector', 'Minimum Frequency', 'Maximum Frequency', 'Channel']} rows={detectorRows}/>
                                    </Item.Description>
                                    <Item.Meta>
                                        <List size='large' bulleted horizontal items={[
                                            {key: '1', content: 'Signal Duration: ' + signalDuration},
                                            {key: '2', content: 'Sampling Frequency: ' + samplingFrequency},
                                            {key: '3', content: 'Trigger Time: ' + triggerTime}
                                        ]}/>
                                    </Item.Meta>
                                </Item.Content>
                            </Item>
                            <Item>
                                <Item.Content>
                                    <Item.Header content={'Model: ' + signalModel.charAt(0).toUpperCase() + signalModel.slice(1)}/>
                                    <Item.Description content={'Injected: ' + signalChoice.charAt(0).toUpperCase() + signalChoice.slice(1)}/>
                                    <Item.Meta>
                                        <List size='large' bulleted horizontal items={[
                                            {key: '1', content: 'Mass 1: ' + mass1},
                                            {key: '2', content: 'Mass 2: ' + mass2},
                                            {key: '3', content: 'Luminosity Distance: ' + luminosityDistance},
                                            {key: '4', content: 'psi: ' + psi},
                                            {key: '5', content: 'iota: ' + iota},
                                            {key: '6', content: 'Phase: ' + phase},
                                            {key: '7', content: 'Merger Time: ' + mergerTime},
                                            {key: '8', content: 'Right Ascension: ' + ra},
                                            {key: '9', content: 'Declination: ' + dec}
                                        ]}/>
                                    </Item.Meta>

                                </Item.Content>
                            </Item>
                            <Item header='Priors' meta={prior.priorChoice}/>
                            <Item header='Sampler' meta={sampler.samplerChoice}/>
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