import React from "react";
import {Grid, Card, Segment} from "semantic-ui-react";
import {createFragmentContainer, graphql} from "react-relay";
import JobResultFile from "./JobResultFile";
import * as Enumerable from "linq";

class JobParameters extends React.Component {
    constructor(props) {
        super(props);
        console.log(this.props)
    }


    render() {
        const {start, jobStatus} = this.props.bilbyJobParameters
        return (
            <React.Fragment>
                <Grid centered textAlign='center' verticalAlign='middle'>
                    <Grid.Row>
                        <Segment compact basic>
                            <Card>
                                <Card.Content header={start.name}/>
                                <Card.Content description={start.description}/>
                                <Card.Content extra content={jobStatus}/>
                            </Card>
                        </Segment>
                    </Grid.Row>
                    <Grid.Row>
                        Job Parameters go here?
                    </Grid.Row>
                </Grid>
            </React.Fragment>
        )
    }
}

export default createFragmentContainer(JobParameters, {
    bilbyJobParameters: graphql`
        fragment JobParameters_bilbyJobParameters on BilbyJobNode {
            jobStatus
            start {
                name
                description
            }
        }
    `
});