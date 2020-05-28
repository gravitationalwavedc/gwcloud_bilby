import React from "react";
import {graphql, createFragmentContainer, commitMutation} from "react-relay";
import {harnessApi} from "../index";

import _ from "lodash";
import BilbyBasePage from "./BilbyBasePage";
import JobResults from "../Components/Results/JobResults";
import JobParameters from "../Components/Results/JobParameters";
import { Divider, Grid, Header, Message, Container, Checkbox, Label, Card, Segment, Tab, Button } from "semantic-ui-react";

class BilbyJobResults extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            private: this.props.data.bilbyJob.start.private
        }
        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: [
                {name: 'Job Results', path: '/bilby/job-results/'}
            ]
        }
    }

    handleSave = (e, data) => {
        this.setState({
            private: data.checked
        })
        commitMutation(harnessApi.getEnvironment("bilby"), {
            mutation: graphql`mutation BilbyJobResultsSetPrivacyMutation($jobId: ID!, $private: Boolean!)
                {
                  updateBilbyJob(input: {jobId: $jobId, private: $private}) 
                  {
                    result
                  }
                }`,
            variables: {
                jobId: this.props.match.params.jobId,
                private: data.checked
            },
            onCompleted: (response, errors) => {
                if (errors) {
                    console.log(errors)
                }
                else {
                    console.log(response)
                }
            },
        })
    }

    render() {
        const {start, jobStatus, lastUpdated, userId} = this.props.data.bilbyJob
        return (
            <BilbyBasePage loginRequired title='Bilby Job Results' {...this.routing}>
                <Grid container stretched textAlign='left'>
                    <Grid.Row verticalAlign='top'>
                        <Grid.Column width={16}>
                            <Grid>
                                <Grid.Column width={8}>
                                    <Header size='huge' content={start.name} subheader={lastUpdated}/>
                                    <Label as={Message} warning>{jobStatus}</Label>
                                    <Label.Group>
                                        <Label>Labels will go here</Label>
                                    </Label.Group>
                                </Grid.Column>
                                <Grid.Column width={8} textAlign='right'>
                                    <Checkbox toggle label={'Private'} onChange={this.handleSave} disabled={harnessApi.currentUser.userId !== userId} checked={this.state.private}/>
                                </Grid.Column>
                            </Grid>
                            <Divider/>
                            <Container textAlign='left'>{start.description}</Container>
                        </Grid.Column>
                    </Grid.Row>
                    <Grid.Column width={16} as={Container}>
                        <Tab menu={{tabular: true, attached: 'top', fluid: true, size: 'huge', widths: 2 }} panes={[
                            { menuItem: {key: 'parameters', icon: 'list', content: 'Parameters'}, render: () => <Tab.Pane><JobParameters bilbyJobParameters={this.props.data.bilbyJob} {...this.props}/></Tab.Pane> },
                            { menuItem: {key: 'results', icon: 'line graph', content: 'Results'}, render: () => <Tab.Pane><JobResults bilbyResultFiles={this.props.data.bilbyResultFiles} {...this.props}/></Tab.Pane> },
                        ]}/>
                    </Grid.Column>
                </Grid>
            </BilbyBasePage>
        )
    }
}

export default createFragmentContainer(BilbyJobResults,
    {
        data: graphql`
            fragment BilbyJobResults_data on Query @argumentDefinitions(
                jobId: {type: "ID!"}
            ){
                bilbyResultFiles(jobId: $jobId) {
                    ...JobResults_bilbyResultFiles
                }
                
                bilbyJob (id: $jobId) {
                    userId
                    jobStatus
                    lastUpdated
                    start {
                        name
                        description
                        private
                    }
                    ...JobParameters_bilbyJobParameters
                }
            }
        `,
    },
);
