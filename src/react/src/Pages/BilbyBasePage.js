import React from "react";
import {Grid, Header, Segment, Breadcrumb} from "semantic-ui-react";
import Breadcrumbs from "../Components/Utils/Breadcrumbs";
import {harnessApi} from "../index";

class BilbyBasePage extends React.Component {
    constructor(props) {
        super(props);
    }


    render() {
        // Make sure user is logged in. If they are not, redirect the user to the login page
        if (this.props.loginRequired && !harnessApi.currentUser) {
            this.props.router.replace("/auth/?next=" + this.props.match.location.pathname)
        }
        return (
            <React.Fragment>
                <Header as='h2' attached='top'>{this.props.title}</Header>
                <Breadcrumbs match={this.props.match} router={this.props.router} paths={this.props.breadcrumbPaths}/>
                <Segment attached id='scrollable'>
                    <Grid centered textAlign='center' style={{minHeight: '100vh'}} verticalAlign='middle'>
                        {this.props.children}
                    </Grid>
                </Segment>
            </React.Fragment>
        )
    }
}

export default BilbyBasePage;
