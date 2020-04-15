import React from "react";
import {Grid, Header, Segment, Breadcrumb} from "semantic-ui-react";
import Link from 'found/lib/Link';
import Breadcrumbs from "../Components/Utils/Breadcrumbs";

class BilbyBasePage extends React.Component {
    constructor(props) {
        super(props);
    }


    render() {
        return (
            <React.Fragment>
                <Header as='h2' attached='top'>{this.props.title}</Header>
                <Breadcrumbs match={this.props.match} router={this.props.router} paths={this.props.breadcrumbPaths}/>
                <Segment attached id='scrollable'>
                    <Grid centered textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                        {this.props.children}
                    </Grid>
                </Segment>
            </React.Fragment>
        )
    }
}

export default BilbyBasePage;
