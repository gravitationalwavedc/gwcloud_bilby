import React from "react";
import {graphql, createFragmentContainer, commitMutation} from "react-relay";
import {harnessApi} from "../index";

import _ from "lodash";
import BilbyBasePage from "./BilbyBasePage";
import JobResults from "../Components/Results/JobResults";
import JobParameters from "../Components/Results/JobParameters";
import { Divider, Grid, Header, Message, Container, Checkbox, Tab, Button, Dropdown } from "semantic-ui-react";
import Link from "found/lib/Link";

import JobStatusMessage from "../Components/Results/JobStatusMessage";
import JobLabelDropdown from "../Components/Results/JobLabelDropdown";
import JobPrivacyToggle from "../Components/Results/JobPrivacyToggle";
import TemporaryMessage from "../Components/Utils/TemporaryMessage";


class BilbyJobResults extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            saved: false,
            saveMessage: null
        }

        this.routing = {
            match: this.props.match,
            router: this.props.router,
            breadcrumbPaths: [
                {name: 'Job Results', path: '/bilby/job-results/'}
            ]
        }
    }

    onSave = (saved, message) => {
        this.setState({
            saved: saved,
            saveMessage: message
        })
    }

    render() {
        const {start, lastUpdated, userId} = this.props.data.bilbyJob

        return (
            <BilbyBasePage loginRequired title='Bilby Job Results' {...this.routing}>
                <TemporaryMessage success={this.state.saved} content={this.state.saveMessage} icon='save' timeout={5000}/>
                <Grid container stretched textAlign='left'>
                    <Grid.Row verticalAlign='top'>
                        <Grid.Column width={16}>
                            <Grid>
                                <Grid.Column width={8}>
                                    <Header size='huge' content={start.name} subheader={lastUpdated}/>
                                    <JobStatusMessage status={this.props.data.bilbyJob} />
                                    <JobLabelDropdown jobId={this.props.match.params.jobId} data={this.props.data} onUpdate={this.onSave} />
                                </Grid.Column>
                                <Grid.Column width={8} textAlign='right'>
                                    <Link as={Button} to={{
                                        pathname: '/bilby/job-form/',
                                        state: {
                                            jobId: this.props.match.params.jobId
                                        }
                                    }} activeClassName="selected" exact match={this.props.match} router={this.props.router}>
                                        Copy Job and Edit
                                    </Link>
                                    <JobPrivacyToggle userId={userId} jobId={this.props.match.params.jobId} data={this.props.data.bilbyJob.start} onUpdate={this.onSave}/>
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
                    lastUpdated
                    start {
                        name
                        description
                        ...JobPrivacyToggle_data
                    }

                    ...JobStatusMessage_status
                    ...JobParameters_bilbyJobParameters
                }

                ...JobLabelDropdown_data @arguments(jobId: $jobId)
            }
        `,
    },
);
